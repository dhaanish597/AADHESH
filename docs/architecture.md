# Aadesh — architecture

Companion to the [foundation spec](superpowers/specs/2026-10-08-aadesh-v2-foundation-design.md).
This document covers the shape of the system and the AWS resources planned. The spec covers
why the decisions were made.

## The integrated chain

```
CAQM source → official invocation → deterministic resolver → Standing Order
          → Step Functions → Cedar authorize → Parchi workflow → worker ack → seal → audit
```

Each arrow is a boundary something could be faked across, and each has a test that says it
cannot be.

### What activates the pipeline (and what does not)

- **Only an official CAQM invocation** activates the legal/compliance workflow. The deterministic
  resolver reads the invoked stage from the verified corpus; an AQI-implied stage **never**
  activates this pipeline.
- **Historical replay is explicitly labelled as replay** and is never treated as a current
  invocation. The corpus carries a revoked Stage III (invoked 16 Jan 2026, revoked 22 Jan 2026);
  `invoked_stage()` returns only an active invocation, and `invocation_history()` exposes the
  replay record.
- A Standing Order is a **pre-commitment, not an autonomous-agent permission**: one site, one
  trigger, explicit actions, explicit validity window, no arbitrary code, no arbitrary agent
  instructions. The Step Functions machine re-checks the recorded supervisor's authority at
  fire time, not just at signing time.

## Ports and adapters

`aadesh_core` is pure Python: **zero AWS imports, zero network, zero clock reads**. Every side
effect crosses a `typing.Protocol` port in `aadesh_core/ports/`.

```
services/
├── aadesh_core/          ← pure. imports nothing but stdlib + jsonschema types
│   ├── domain/           value objects, enums, the UNKNOWN_FACT sentinel
│   ├── ports/            13 Protocols: the only way out
│   ├── resolver/         site × stage × corpus → ObligationSet   (pure function)
│   ├── parchi.py         DRAFT → PENDING_ACK → ACKNOWLEDGED → SEALED | VOID
│   ├── parchi_ack/       tokens, roster, events, the service, the workflow contract
│   ├── stages.py         invoked vs implied, from cited bands only
│   ├── verification/     re-prove citations against hashed bytes
│   ├── explanation/      the output contract + deterministic text
│   └── corpus_schemas/   JSON Schemas (with the CODE, not the corpus)
├── aadesh_adapters/      ← everything that touches the world
│   ├── sources/          PDF bytes → citable page text (pypdf, imported lazily)
│   ├── store/            parchi store, acknowledgement tokens, idempotency ledger
│   ├── audit/            audit records, rendered as flat text
│   └── corpus/           the join between verification and resolution
└── aadesh_cli/           `aadesh-verify`, `aadesh-corpus`, and `aadesh-parchi`
```

A Lambda handler and the local HTTP server are both thin adapters calling the same core
functions. That is what makes "the same logic runs locally and on AWS" true rather than a
claim.

## Where the model is, and is not

```
                   ┌──────────── ENFORCEMENT PATH ────────────┐
reading ──▶ corpus ──▶ verify ──▶ resolve ──▶ Cedar ──▶ parchi ──▶ ack ──▶ sealed
                   └──────────────────────────────────────────┘
                                       │
                                       ▼  (read-only, after the fact)
                            Bedrock + Strands ──▶ contract check ──▶ show
                                       │ fails
                                       ▼
                              deterministic text
```

Bedrock gets two jobs: render an already-computed result into plain language, and answer a
question by citing already-computed results. Its output is checked against
`aadesh_core.explanation.check_explanation` and `check_grounding` before a user sees it.
**The model can be entirely unavailable and Aadesh still works.**

### AI explains; deterministic code decides

The explanation layer is documented in full in [explanation-layer.md](explanation-layer.md).
Three properties hold by construction:

- The deterministic result (`ResolutionResult` / `Parchi`) is retained **separately** from the
  model response and is never replaced by it. If the two disagree, the deterministic result
  wins.
- The model receives a structured, PII-free `ExplanationRequest` and may only cite the
  citations it contains. Hallucinated citations, hashes, stages and replays are rejected and
  the deterministic text is shown (`UNSUPPORTED`).
- The explanation endpoint goes through Cedar first, using `ViewSiteExecution` for a site and
  `ViewParchi` for a Parchi. On a denial the model is never called. There is no backdoor around
  the facilitator privacy boundary.

**An LLM response is never authoritative evidence.** It is presentation only; compliance
resolution, authorization, obligation status and Parchi state are computed without it.

## Authorization and acknowledgement: two boundaries, not one

Cedar (Prompt 6) and the Parchi workflow (Prompt 5) are separate boundaries. Neither is the
sole security layer.

### Cedar authorizes actions; it does not decide legal obligations

Cedar answers "may this principal perform this action on this resource?" and nothing else. It
does not decide which obligation applies, whether restrictions activate, or whether a
transition is legal. `Parchi.state` is carried as an attribute that no rule reads, and a test
asserts Cedar still PERMITS a transition the domain then refuses -- so the two cannot drift
into being a second state machine.

The five boundaries:

| Principal | May | May NOT |
|---|---|---|
| Supervisor | IssueHalt only on an assigned site | Acknowledge a worker's Parchi |
| Worker | AcknowledgeOwnParchi for their own Parchi | Acknowledge another worker's Parchi |
| Facilitator | AssistClaim only under granted, unrevoked, unexpired consent | ViewParchi |

### The Parchi workflow: acknowledgement and sealing are separate acts

`parchi.py` holds the transitions: `DRAFT → PENDING_ACK → ACKNOWLEDGED → SEALED`, with
`VOID` reachable from any non-terminal state. `parchi_ack/service.py` holds the only code
that may move a record along it.

Three properties are load-bearing, and each has a mechanism rather than an intention:

| Property | Mechanism |
|---|---|
| Only the named worker can confirm | The actor is compared to `parchi.worker_id` **before** the idempotency ledger is consulted, so the rule applies to replays too |
| A link is single-use, and a double tap is one fact | `AcknowledgementTokenStore.consume` is a compare-and-set; `IdempotencyLedger.execute_once` runs the confirmation at most once per token hash and hands every later caller the first result |
| Two workflow retries cannot open two parches for one worker | `ParchiAckStore.save_new` is a conditional create on `idempotency_key`; the loser writes nothing and reads back the winner |

**The QR payload is `aadesh://ack/<token>` and nothing more.** No worker id, no parchi id, no
site, no JSON, no name, no contact detail. The token is 256 bits of `secrets.token_urlsafe`,
stored only as a SHA-256 hash; audits carry a 16-character reference derived from that hash, so
a dump of the database or the audit log yields no usable links. Rejections are uniform: the
caller sees one sentence whatever went wrong, and the reason is a separate field the caller is
never shown, so the error cannot be used to probe for valid tokens.

### PENDING_ACK / task-token integration

The Step Functions machine (Prompt 4) and the Parchi workflow (Prompt 5) are connected through
the `WorkflowExecution` / `ParchiProvenance` / `Roster` interface in `parchi_ack/workflow.py`.

1. The machine creates Parchis via `create_parchis_for_roster(...)` -- leaves them PENDING_ACK.
2. The machine **waits durably** for worker acknowledgement via
   `lambda:invoke.waitForTaskToken` -- no polling, no frontend timer.
3. The worker confirms via `acknowledge_parchi(...)` -- Cedar allows, the domain checks the
   worker identity, the token is consumed compare-and-set, the acknowledgement event is recorded.
4. The machine resumes and continues toward sealing via `seal_parchi(...)`.
5. The audit log records the evidence.

PENDING_ACK cannot directly become SEALED: sealing requires ACKNOWLEDGED first. If it were
reachable, a supervisor could produce a sealed record that no worker ever confirmed -- which
is the one thing the parchi exists to make impossible.

### Idempotency: three levels

| Level | Scenario | Guarantee |
|---|---|---|
| 1. Trigger | Same official trigger twice | One workflow execution (TriggerRunStore.claim, create-if-absent) |
| 2. Parchi | Same worker/workflow twice | One Parchi (ParchiAckStore.save_new, conditional create on idempotency_key) |
| 3. Acknowledgement | Same worker/token twice | One acknowledgement event (IdempotencyLedger.execute_once) |

The idempotency key for Parchi creation is derived deterministically from the workflow
execution id and worker id (`f"{execution_id}:{worker_id}"`), so a Step Functions retry
recomputes the same key and finds the parchi the first attempt created. This is the join
between Prompt 4's fingerprint-based dedup and Prompt 5's per-worker parchi creation.

## AWS resources planned

Nothing below is deployed yet. The core vertical slice runs locally first, by design.

| Service | Resource | Job |
|---|---|---|
| **S3** | `aadesh-sources-<acct>` | exact downloaded CAQM order bytes, keyed by SHA-256 |
| **DynamoDB** | `aadesh-readings` (PK `station_id`, SK `observed_at`) | station readings with provenance |
| **DynamoDB** | `aadesh-parchis` (PK `parchi_id`, GSI `site_id`, GSI `worker_id`) | parchi records |
| **DynamoDB** | `aadesh-standing-orders` (PK `standing_order_id`, GSI `site_id`) | pre-committed triggers |
| **DynamoDB** | `aadesh-sites` (PK `site_id`) | site profile and roster |
| **Lambda** | `ingest-reading` (py3.13) | EventBridge-driven station poll |
| **Lambda** | `resolve-obligations` (py3.13) | wraps the pure resolver |
| **Lambda** | `create-standing-order` / `open-parchis` / `acknowledge-parchi` / `assist-claim` | the write path |
| **Lambda** | `explain` (py3.13) | Strands → Bedrock, contract-checked |
| **EventBridge** | 15-minute schedule rule + stage-trip bus | makes the system event-driven |
| **Step Functions** | `standing-order` state machine | holds `PENDING_ACK` durably across hours |
| **Cognito** | user pool, 3 groups | supervisor / worker / facilitator identity |
| **API Gateway** | HTTP API | the routes the local dev server mirrors exactly |
| **CloudWatch** | log groups + audit metric filter | the audit trail |
| **Amplify Hosting** | Next.js app | the public URL a judge can open |
| **OpenSearch** | `aadesh-corpus-pages` | citation search, and the opt-in `--with-index` check |

Cedar is **not** an AWS service here: it runs in-process via the `cedarpy` native binding, so
authorization works identically in a Lambda, in a local server, and in a unit test, with no
network hop. AWS Verified Permissions was considered and rejected for exactly that reason.

OpenSearch runs in Docker locally. Managed OpenSearch is likely to exceed the free tier, and
using an AWS open-source project is independently sufficient for hackathon eligibility.

## Local development

```bash
make setup     # uv venv + deps.    no Docker, no AWS account
make test      # pytest + fakes.    no Docker.  ~2s
make verify    # citation proof.    no Docker
make lint
```

Opt-in only: `make test-integration` (LocalStack), `make verify-index` (OpenSearch).

The default path must never require Docker, credentials, or a network. That is not just
convenience — it is what lets a judge clone the repo cold and run the central proof.

## Provenance and security invariants

Every actionable obligation retains: source document, page, quote, source hash, evidence/citation.
Parchi creation does not replace or obscure the original evidence; a Parchi references the
compliance event/obligation that caused it. It must remain possible to answer "Why was this
Parchi created?" with a deterministic chain back to:

CAQM source → official invocation → resolver → obligation → Standing Order execution → Parchi

### After integration, these remain true:

1. AQI alone cannot trigger a legal workflow.
2. Historical invocation cannot appear as current.
3. Unknown facts remain UNKNOWN.
4. Missing citation cannot create an actionable obligation.
5. Tampered corpus cannot create verified obligations.
6. Worker A cannot acknowledge Worker B's Parchi.
7. Supervisor cannot acknowledge a worker's Parchi.
8. Facilitator cannot view the complete Parchi.
9. Facilitator cannot assist without explicit consent.
10. Expired consent cannot authorize assistance.
11. Expired QR token cannot acknowledge.
12. Used QR token cannot be reused.
13. Duplicate workflow trigger cannot create duplicate Parchis.
14. Duplicate acknowledgement cannot create duplicate events.
15. SEALED Parchi cannot be modified.
16. PENDING_ACK cannot directly become SEALED.
17. Cedar failure fails closed.
18. LLM is not required for authorization.
19. LLM is not required for compliance resolution.
20. No monetary entitlement amount is invented.

### Replay / current separation

The current verified corpus has historical Stage III: invoked 2026-01-16, revoked 2026-01-22.
Current mode reports no active invocation. No fake current Stage III is created for demo
convenience. The explicit replay/simulation mechanism visibly distinguishes CURRENT from
HISTORICAL REPLAY.
- **SAM CLI is not installed** on the current dev machine, so `sam local` is untested.
- **AWS adapters are not written** beyond the ports they will satisfy. Deliberate: the core
  slice had to work locally first. The in-memory store, token store and ledger are the same
  interfaces a DynamoDB adapter will satisfy, and are single-process only — see
  `ports/parchi_ack.py` for what a real implementation must guarantee.
- **No HTTP surface yet.** `aadesh-parchi` is a CLI over the same core calls a Lambda handler
  will make.
- **Step Functions ASL is committed but not deployed.** `infra/stepfunctions/standing-order.asl.json`
  defines the machine; the Lambda handlers that back each step are not yet written. The core
  vertical slice runs locally first, by design.
- **Cedar is wired into authorization tests**, but the CLI acknowledgement path uses the domain
  identity rule directly (the worker-identity check) rather than going through Cedar -- because
  the identity rule is a domain invariant, not an access-control policy. The `AuthorizationProvider`
  port is available for the API layer to use.
