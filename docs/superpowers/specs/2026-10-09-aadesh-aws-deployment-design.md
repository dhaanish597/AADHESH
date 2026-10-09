# Aadesh — AWS deployment design

**Date:** 2026-10-09
**Status:** awaiting review
**Account:** 375546530800 · **Region:** `ap-south-1` (Bedrock client pinned to `us-east-1`)
**Companion to:** [foundation spec](2026-10-08-aadesh-v2-foundation-design.md), [architecture](../architecture.md)

---

## 1. Purpose

Deploy Aadesh to AWS so the full console runs against a real backend, and document every
resource. The system exists locally today and proves its central claim offline: the
deterministic core resolves obligations from a verified corpus, Cedar authorizes every
transition in-process, and `make verify` re-proves 55 citations against hashed bytes.

Deployment must preserve that claim rather than replace it. **The same core functions run in
the local server and in Lambda** — a thin adapter either side. Anything that made the cloud
path a second implementation would defeat the project's purpose.

### Success criteria

- The console is reachable at a public Amplify URL and logs in through Cognito.
- All 12 verification flows (§13) execute against the deployed backend and are recorded.
- Every AWS resource has a stated responsibility, and the excluded services have stated reasons (§3).
- No secret, key or personal datum is committed (§10).
- `make test`, `make verify` and `make api` keep working offline with no AWS account, exactly as today.

### Non-goals

Not a production hardening exercise, not multi-region, not multi-site (§16). One entity type
stays frozen: `construction_site`.

---

## 2. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D1 | Real deploy to account 375546530800, resources retained | Requested |
| D2 | OpenSearch runs **locally in Docker only**; no AWS resource | A managed domain starts ~$25–50/mo for a citation search `make verify` already performs correctly against hashed bytes |
| D3 | Cognito **full**: pool + 3 groups, login UI, JWT authorizer, principal from claims | Otherwise `_principal()` stays a hardcoded string and the worker-identity invariant is unfalsifiable |
| D4 | Verification flow 4 demonstrates the **labelled historical replay** | No verified current invocation exists; the corpus records a revoked Jan-2026 Stage III. Inventing one is the failure mode the project refuses |
| D5 | Push to GitHub, **git-connected Amplify** | Auto-deploy on push; also puts the code on GitHub |
| D6 | **Live OpenAQ** ingestion, `provenance=MEASURED` | "Latest reading" should be genuine. Requires an OpenAQ API key supplied by the operator |
| D7 | Approach A — shared `AadeshApplication`, thin Lambda skins | Local server and Lambda provably share code |
| D8 | **One** container-image `workflow` Lambda for all seven ASL steps | Avoids seven byte-identical bundles of the same core; the ASL's seven ARNs point at one function with an `action` field |
| D9 | CDK in Python | Installed (2.1142.0), matches the repo's language, bundles the ASL and policies in one app |
| D10 | Four stacks, all stateful resources `RemovalPolicy.RETAIN` | A Lambda change must not re-run the slow Amplify deploy; a stack update must never delete the corpus or the parchis |

---

## 3. AWS resource set

| Service | Resource | Responsibility |
|---|---|---|
| S3 | `aadesh-sources-375546530800-ap-south-1`, versioned, SSE-S3 | Authoritative CAQM bytes, extracted page text, corpus JSON |
| DynamoDB | 6 tables (§3.1) | Parchi records, ack tokens, idempotency ledger, standing orders, trigger fingerprints, readings, site rosters |
| Lambda | 5 functions (§4.2) | `api`, `ingest-reading`, `workflow`, `explain`, `verify` |
| API Gateway | HTTP API + `$default` stage | Sole public HTTPS entry point; hosts the JWT authorizer and per-route throttles |
| Cognito | user pool, 3 groups, hosted-UI domain, 1 app client | Source of principal identity |
| EventBridge | 1 rule, `rate(15 minutes)` | Drives ingestion without a human |
| Step Functions | `standing-order` machine | Only mechanism that holds `PENDING_ACK` across hours with no frontend timer |
| CloudWatch | 1 log group per function (90-day retention), 1 metric filter, 1 alarm | AWS sink for the `AuditLog` port; alarm on authorization denials |
| Amplify Hosting | 1 app, git-connected, root `web/` | Serves the console, runs its own build |
| Bedrock | Claude via Converse API, `us-east-1` | Explanation only, contract-checked |
| IAM | 5 roles, one per function (§11) | Least privilege |
| SSM | 2 `SecureString` parameters (§10) | OpenAQ key, QR signing secret |

### 3.1 DynamoDB tables

| Table | Key | Billing | Items |
|---|---|---|---|
| `aadesh-parchis` | PK `parchi_id`; GSI `site_id`, GSI `worker_id`, GSI `idempotency_key` | On-demand | Parchi records |
| `aadesh-operational` | PK `pk` = `<kind>#<id>`, TTL on `expires_at` | On-demand | Three namespaced kinds: `acktoken#`, `ledger#`, `tasktoken#` |
| `aadesh-standing-orders` | PK `standing_order_id`; GSI `site_id` | On-demand | Pre-committed triggers |
| `aadesh-trigger-runs` | PK `fingerprint` | On-demand | Create-if-absent trigger dedup |
| `aadesh-readings` | PK `station_id`, SK `observed_at` | On-demand | Station readings with provenance |
| `aadesh-sites` | PK `site_id` | On-demand | Site profile + roster (today hardcoded as `WORKER_COUNT = 34`) |

`aadesh-operational` is one table rather than three because all three kinds are small,
hash-keyed, short-lived coordination records with no cross-record query. They share a TTL
mechanism and nothing else would be gained by splitting them.

### 3.2 Deliberately excluded

| Not used | Reason |
|---|---|
| AWS Verified Permissions | Cedar runs in-process via `cedarpy`. A network hop would make authorization fail *differently* in Lambda than in a unit test — the one property this project cannot trade |
| Secrets Manager | SSM `SecureString` is KMS-backed and free at this scale, against $0.40/secret/month |
| SQS / SNS | EventBridge invokes Lambda directly. A queue between them would add no guarantee we need |
| CloudFront | Amplify ships its own CDN |
| Cognito identity pool | The browser never calls an AWS service directly, so federated AWS credentials have no purpose |
| RDS / Aurora | Every access is a key lookup; no joins in the hot path |
| ElastiCache | `/tmp` corpus materialisation plus DynamoDB is sufficient at this scale |
| Kinesis / Firehose | No streaming requirement |
| ECS / Fargate | Nothing is long-running except Step Functions, which is serverless |
| Managed OpenSearch | See D2 |
| WAF | Out of scope; recorded as a known gap in §17, not silently omitted |

---

## 4. Ports to adapters

### 4.1 The map

| Port | Local adapter (exists) | AWS adapter (new) | Backs onto |
|---|---|---|---|
| `AuthorizationProvider` | `CedarAuthorizationProvider` | **unchanged** | nothing — policies bundled in image |
| `Clock` | `SystemClock` | **unchanged** | nothing |
| `RulesCorpus` + `SourceDocumentStore` + `InvokedStageSource` | `LocalFileCorpus` | `S3Corpus` | S3 → `/tmp` |
| `AqiProvider` | `FixtureAqiProvider` | `OpenAQProvider` | OpenAQ v3 → `aadesh-readings` |
| `AuditLog` | `RecordingAuditLog`, `StdoutAuditLog` | `CloudWatchAuditLog` | stdout → Logs + EMF |
| `ParchiStore` + `ParchiAckStore` | `InMemoryParchiStore` | `DynamoParchiStore` | `aadesh-parchis` |
| `AcknowledgementTokenStore` | `InMemoryAcknowledgementTokenStore` | `DynamoAcknowledgementTokenStore` | `aadesh-operational` |
| `IdempotencyLedger` | `InMemoryIdempotencyLedger` | `DynamoIdempotencyLedger` | `aadesh-operational` |
| `StandingOrderStore` | *none exists* | `DynamoStandingOrderStore` | `aadesh-standing-orders` |
| `TriggerRunStore` | *none exists* | `DynamoTriggerRunStore` | `aadesh-trigger-runs` |
| `CitationVerifier` | `SourceBytesCitationVerifier` | same, + `OpenSearchCitationVerifier` | local Docker |
| **`TaskTokenStore`** | *new port* | `DynamoTaskTokenStore` | `aadesh-operational` |

`AuthorizationProvider` and `Clock` needing no new adapter is the property the authorization
story rests on: **Cedar and time behave identically in a unit test and in a Lambda.**

`StandingOrderStore` and `TriggerRunStore` have no implementation anywhere today, not even
in-memory — `server.py` holds the order in `self.order`. These are new, not re-pointed.

### 4.2 New port: `TaskTokenStore`

`infra/stepfunctions/standing-order.asl.json` passes `task_token` to
`aadesh-parchi-ack-waiter`, but nothing in the codebase persists a task token. Without one, a
worker's acknowledgement cannot resume the waiting execution.

```python
@runtime_checkable
class TaskTokenStore(Protocol):
    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None: ...
    def pop(self, *, parchi_id: str) -> str | None:
        """Read and remove in one step. Removing on read makes a retried resume a no-op."""
        ...
```

Implemented by `InMemoryTaskTokenStore` (local) and `DynamoTaskTokenStore` (delete-on-read
via `DeleteItem` with `ReturnValues=ALL_OLD`).

### 4.3 The `AadeshApplication` refactor

`services/aadesh_web/server.py`'s `Demo` constructs `InMemoryParchiStore()`,
`LocalFileCorpus()` and `InMemoryAcknowledgementTokenStore()` inside its own `__init__`, so it
cannot run against DynamoDB. It becomes `AadeshApplication`, constructed from an injected
bundle of ports.

- `services/aadesh_web/server.py` keeps its `http.server` skin, injects memory + `local_file`,
  so `make api` and `make test` are unchanged.
- `services/aadesh_lambda/handlers/api.py` is an API Gateway skin injecting DynamoDB + S3 + OpenAQ.

`Demo`'s process-local `self._payloads` dict becomes a `ParchiStore` query, because it does not
survive a container.

**Guard test:** both skins expose the same route set and produce the same response shape for
the same injected ports — the same discipline `test_asl_matches_core_machine.py` already
applies to the state machine, so the local demo and the deployed backend cannot silently drift.

---

## 5. Lambda functions

All five ship as **container images from one shared base image**, differing only in `CMD`.
`cedarpy` is a native Rust binding, so a Linux build is mandatory; one image sidesteps the
seven-identical-bundle problem and guarantees the same native binding everywhere.

- Base: `public.ecr.aws/lambda/python:3.13`, architecture **x86_64** (both arches have cp313
  manylinux wheels; arm64 is a later ~20% saving, not a correctness question).
- Build context: repo root, with a `.dockerignore` excluding `.git`, `.venv`, `node_modules`,
  `web/.next`, `__pycache__`.
- Layer contents: `services/`, `corpus/`, `infra/cedar/`.

| Function | Trigger | Action |
|---|---|---|
| `aadesh-api` | API Gateway HTTP API | Routes to `AadeshApplication`; principal from JWT claims |
| `aadesh-ingest-reading` | EventBridge `rate(15 minutes)` | OpenAQ v3 → `aadesh-readings` |
| `aadesh-workflow` | Step Functions (7 ARNs → 1 function) | Dispatches on `action`: `stage-trip`, `resolve`, `authorize`, `create-parchis`, `ack-waiter`, `seal`, `audit` |
| `aadesh-explain` | API Gateway (route) | Bedrock + Strands; contract-checked, deterministic fallback |
| `aadesh-verify` | API Gateway (route) | `run_verify` over the S3-materialised corpus |

The ASL's seven `Resource` ARNs point at `aadesh-workflow` with an `action` field. Step order
and the `waitForTaskToken` contract are unchanged; `test_asl_matches_core_machine.py` keeps
guarding the semantics and gains the assertions in §7.2.

---

## 6. Identity: Cognito to `Principal` to Cedar

Verified against `infra/cedar/policies.cedar`, `infra/cedar/schema.cedarschema.json` and
`aadesh_core/authorization/resources.py`.

| Cognito source | `Principal` field | Constraint |
|---|---|---|
| `cognito:groups[0]` | `role` | Exactly `supervisor` / `worker` / `facilitator` — the policy compares `principal.role == "supervisor"` |
| `custom:principal_id` | `principal_id` | **Must equal `parchi.worker_id`** — e.g. `worker-001`. `parchi_resource()` builds `EntityRef("Principal", parchi.worker_id)` and the rule is `resource.worker == principal`, i.e. entity equality on the id. A Cognito `sub` UUID can never satisfy it |
| `custom:assigned_site` | `assigned_site` | Must equal the `Site` resource's `siteId` (`example-piling-site`), because the rule is `resource.siteId == principal.assignedSite` |

### 6.1 The custom-attribute write risk

Cognito custom attributes are **user-writable** on a default app client. If a worker could
write `custom:principal_id`, they would set it to `worker-002` and acknowledge another
worker's parchi — defeating the exact invariant the `no-proxy-acknowledgement` forbid rule
enforces.

**Mitigation, enforced in CDK:** the `UserPoolClient` is created with `writeAttributes`
excluding `custom:principal_id` and `custom:assigned_site`, and group membership is assigned
only through the admin API. A deployment test asserts the client's write-attribute set does
not contain either.

### 6.2 The flaw this closes

`services/aadesh_web/server.py` takes `worker_id` from the request body:

```python
demo.acknowledge(str(body.get("payload", "")), str(body.get("worker_id", "")))
```

and `Demo.acknowledge` builds `Principal(principal_id=worker_id, role="worker")` from it.
Locally this is a documented demo shortcut. On a public URL it means any client can
acknowledge any worker's parchi by naming them, because `resource.worker == principal` is then
satisfied by the caller's own claim.

**On AWS the principal comes only from verified JWT claims.** The body's `worker_id` is
ignored; a mismatch is `403`. This makes verification flow 8 a real Worker-A-against-Worker-B
test rather than an assertion. The same rule applies to the facilitator id and the supervisor's
site: neither may be named by the request.

---

## 7. Workflow and task tokens

### 7.1 The round trip

1. EventBridge / API → Step Functions `StartExecution`.
2. `StageTrip` → `workflow` `action=stage-trip` → S3 corpus → evaluate the trigger.
3. `ResolveObligations` → `action=resolve` → pure resolver.
4. `Authorize` → `action=authorize` → Cedar re-checks the recorded supervisor's authority **at
   fire time**, not only at signing time.
5. `CreateParchis` → `action=create-parchis` → `create_parchis_for_roster` → `DynamoParchiStore.save_new`
   (conditional create on `idempotency_key`) → returns parchi ids + worker ids.
6. `PendingAck` Map → `AwaitWorkerAck` (`lambda:invoke.waitForTaskToken`) → `action=ack-waiter`
   stores the token at `tasktoken#<parchi_id>` with a TTL matching the timeout, then **returns
   without completing the token**.
7. Worker scans the QR, the console calls `POST /api/worker/acknowledge` with a JWT. The api
   Lambda: principal from claims → `AuthorizationService.acknowledge_own_parchi` (Cedar, then
   the domain's own identity rule) → token CAS consume → ledger `execute_once` →
   `ACKNOWLEDGED` → audit.
8. The **api Lambda** then `pop`s `tasktoken#<parchi_id>` and calls `sfn:SendTaskSuccess` — the
   acknowledgement write and the workflow resume happen in the same invocation, so a worker
   never has to poll for the machine to notice.
9. Machine resumes → `SealParchis` → `action=seal` → `SEALED` → audit.

### 7.2 A defect in the committed ASL

`AwaitWorkerAck` has **no `TimeoutSeconds` and no `HeartbeatSeconds`**. A
`lambda:invoke.waitForTaskToken` task defaults to a **one-year** timeout. With
`MaxConcurrency: 10` over a 34-worker roster, one unscanned QR leaves an execution — and its
billing — alive for a year.

Consequently the iterator's `AckTimeout` state is **unreachable**: nothing can produce the
timeout error it catches, so the committed machine's timeout branch is dead code.

**Fix:** add `TimeoutSeconds` (86400) and `HeartbeatSeconds` to `AwaitWorkerAck`.
`test_asl_matches_core_machine.py` is extended to assert the timeout is present and the
`AckTimeout` branch is reachable — a stronger test than the one it replaces.

### 7.3 Failure handling

| Case | Handling |
|---|---|
| `SendTaskSuccess` after the machine timed out | `TaskTimedOut` / `InvalidToken` is caught and audited, **never surfaced to the worker**. The acknowledgement genuinely succeeded; conflating the two would report a true fact as a failure |
| Lambda retry after a successful resume | Delete-on-read makes the second `pop` return `None`, so no second `SendTaskSuccess` |
| Duplicate trigger | `TriggerRunStore.claim` create-if-absent; parchi ids are deterministic from `(fingerprint, worker_id)` |
| Two concurrent acknowledgements on one token | `consume` is a compare-and-set; the loser raises `TokenRejected` and writes nothing |
| Malformed / unparseable model output | `ExplanationService` falls back to deterministic text and reports `UNSUPPORTED` |

---

## 8. Corpus, S3 and search

### 8.1 Layout

S3 mirrors `corpus/` one-to-one: `sources/manifest.json`,
`sources/<doc_id>/pN.txt`, `sources/<doc_id>.pdf`, `obligations/construction_site.json`,
`entitlements/cess_fund.json`, `stage_bands/grap_stage_bands.json`, `invoked_stage.json`.

### 8.2 `S3Corpus`

Materialises to `/tmp/aadesh-corpus`, keyed by the S3 `versionId` of `manifest.json` (bucket is
versioned, so `versionId` is a real change token). Cold start syncs; warm start compares the
version and skips.

`LocalFileCorpus.snapshot()` re-hashes every source document on every call, by design. Bundling
the corpus into the image instead would make S3 decorative and would make `verify` hash the
image's copy rather than the authoritative bytes — so materialisation is the mechanism that
keeps "verification hashes the bytes you actually have" true in the cloud.

### 8.3 Deploy-time byte assertion

The corpus is uploaded with `ChecksumAlgorithm=SHA256`. The deploy then asserts each object's
reported `ChecksumSHA256` decodes to the `sha256` in `manifest.json`, and **fails the deploy on
a mismatch**. A tampered, re-encoded or partially-uploaded object can therefore never reach the
deployed system, so the cloud inherits the tamper-refusal `make verify-tamper` demonstrates
locally. This is a deploy-time gate, not a runtime hope.

### 8.4 OpenSearch, local only

`OpenSearchIndex` indexes page text and citations into `aadesh-corpus-pages` in Docker.
`OpenSearchCitationVerifier` implements `CitationVerifier` and asserts the index agrees with
the byte-level verification — which is what `make verify-index` was always meant to
check. **No AWS resource exists for it** (D2); the deployment docs state the cost reason
plainly rather than implying it was forgotten.

---

## 9. Frontend deployment

Amplify Hosting, git-connected to `github.com/dhaanish597/AADHESH`, app root `web/`.

The console keeps its same-origin design: `next.config.mjs` rewrites `/api/:path*` to
`AADESH_API_URL`, so there is no CORS surface and no second source of truth. Amplify is given
`AADESH_API_URL` from the API Gateway URL (the Amplify stack depends on the backend stack).

**Prerequisite:** the repo has **zero commits on GitHub** — `web/` and `services/aadesh_web/`
are entirely untracked and 54 changes are uncommitted. Everything is committed and pushed
before Amplify is connected.

### 9.1 New frontend surface

- `/login` — Cognito hosted UI redirect; tokens handled client-side.
- `/auth/callback` — code exchange.
- `lib/api.ts` gains an `Authorization: Bearer <idToken>` header and redirects to `/login` on `401`.
- A role-aware shell: the three pages (`/supervisor`, `/worker`, `/facilitator`) render for the
  role in the token, and the existing role switcher becomes a demonstration affordance rather
  than the identity source.

### 9.2 Callback URL trade-off

Cognito needs the Amplify callback URL, but Amplify's default domain contains a generated app
id — a genuine circular reference between the Identity and Frontend stacks.

**Accepted for now:** callback URLs are `http://localhost:3000/auth/callback` and
`https://*.amplifyapp.com/auth/callback`, so the deploy completes in one pass. The wildcard is
narrower than ideal: any `amplifyapp.com` app could present itself as a callback. The
tightening path is a one-line CDK context change once the real domain is known, and it is
documented rather than hidden. A two-pass manual deploy was rejected as worse.

---

## 10. Secrets and configuration

| Secret | Store | Consumer |
|---|---|---|
| OpenAQ API key | SSM `SecureString` `/aadesh/prod/openaq-api-key` | `aadesh-ingest-reading` |
| QR signing secret | SSM `SecureString` `/aadesh/prod/qr-signing-secret` | `aadesh-api` |
| GitHub token (Amplify) | CDK context / SSM, **never committed** | deploy only |

Lambda environment variables carry only table names, bucket name, pool id, region and backend
selectors — **no secrets**.

`.env.example` gains the deployment variables (table names, bucket, pool id, client id,
Bedrock region and model id) with safe local defaults preserved, so a fresh clone still runs
offline. `.env` stays gitignored.

**Removed, not migrated:** `NEXT_PUBLIC_API_BASE_URL=http://localhost:3001`. Nothing reads it —
`next.config.mjs` proxies through `AADESH_API_URL`, and the console calls relative paths
(`web/lib/api.ts`). Its port (`3001`) contradicts the local API's actual port (`8787`), so
leaving it in place would be a comment that lies. The proxy variable is the only one the
frontend needs.

**Guard test:** `test_source_scan_guard.py` is extended to fail the build on `AKIA`,
`aws_secret_access_key`, a live OpenAQ key pattern, or the QR signing secret appearing anywhere
in the tree. The existing pattern for scanning source is reused rather than a new mechanism.

**Operator prerequisites:** an OpenAQ API key (D6) and an authorised GitHub token (D5). Neither
can be created by this work.

---

## 11. IAM, least privilege

One role per function. `workflow`'s role is the **union** across its seven steps — the honest
price of D8.

| Function | Grants | Notable denial |
|---|---|---|
| `api` | DynamoDB RW on parchis / operational / sites / standing-orders; `ssm:GetParameter` on the QR secret only; `states:SendTaskSuccess` + `SendTaskFailure` on one execution ARN; `s3:GetObject` + `s3:ListBucket` on the corpus prefix | no Bedrock; no `s3:PutObject` |
| `ingest-reading` | `ssm:GetParameter` on the OpenAQ key only; `dynamodb:PutItem` + `Query` on readings | no corpus access; no parchi access |
| `workflow` | corpus read; DynamoDB RW on parchis / standing-orders / trigger-runs / operational; `bedrock:InvokeModel` on one model ARN; `states:SendTaskSuccess` on one execution ARN | — |
| `explain` | `bedrock:InvokeModel` on one model ARN; DynamoDB **read-only** on parchis / standing-orders; corpus read | **zero write permissions — the explanation path physically cannot mutate state** |
| `verify` | `s3:GetObject` + `s3:ListBucket` on the corpus prefix | nothing else |

Model ARNs and the execution ARN are named specifically, never `*`.

**Reserved concurrency:** `ingest-reading` = 1 (a concurrent second poll would store a
duplicate of the same reading), `explain` = 5 (bounds Bedrock spend). Both are real
responsibilities.

**CloudWatch:** one log group per function with explicit 90-day retention; a metric filter on
the audit JSON for authorization denials; one alarm whose threshold sits above the normal
traffic of the Cedar demonstration page, which deliberately produces denials, so that the alarm
means something rather than firing constantly.

---

## 12. Local development stays unchanged

`make setup`, `make test`, `make verify`, `make verify-tamper`, `make resolve`, `make api` and
`make web` keep working with no Docker, no AWS account and no network. That is asserted, not
hoped: the default test path never constructs an AWS adapter.

New opt-in targets, in the existing style (never on the default path):

| Target | What it does | Needs |
|---|---|---|
| `make test-aws` | adapter contract tests against LocalStack | Docker |
| `make deploy` | `cdk deploy --all` | AWS credentials |
| `make sync-corpus` | upload `corpus/` and assert checksums (§8.3) | AWS credentials |
| `make seed-sites` | write site + roster to `aadesh-sites` | AWS credentials |
| `make verify-index` | existing target, extended to assert the OpenSearch agreement | Docker |

---

## 13. The 12 verification flows

Every flow is executed against the deployed backend and its evidence recorded.

| # | Flow | How it is proven |
|---|---|---|
| 1 | Login | Cognito hosted-UI login for three users (supervisor / worker / facilitator); a request with no token or an expired token returns `401` |
| 2 | Site selection | `GET /api/sites` reads `aadesh-sites`; the console selects; resolution scoped to the chosen site |
| 3 | Latest reading | EventBridge fires → OpenAQ → `aadesh-readings`; the console shows value, `observed_at`, age and `provenance=MEASURED` |
| 4 | Official invocation | **Labelled historical replay**: Stage III invoked 2026-01-16, revoked 2026-01-22, with the replay banner. CURRENT mode honestly reports none (D4) |
| 5 | Obligation resolution | `POST /api/resolve` over the S3 corpus → obligations with clause id, page, verbatim quote and source hash |
| 6 | Standing Order | Supervisor creates one → Cedar `IssueHalt` allows → Step Functions execution starts and is visible in the console |
| 7 | Parchi | `CreateParchis` mints 34 parchis in DynamoDB, `PENDING_ACK`, QR payloads `aadesh://ack/<token>` |
| 8 | Worker acknowledgement | Worker JWT + QR payload → `ACKNOWLEDGED` → `SendTaskSuccess` resumes the machine → `SEALED`. **Plus a Worker-A-against-Worker-B attempt, which returns `403`** — testable only now that identity is real (§6.2) |
| 9 | Cedar denial | The supervisor's token attempts `AcknowledgeOwnParchi` → denied by the `no-proxy-acknowledgement` forbid, with its policy id shown |
| 10 | Facilitator redaction | Facilitator token: `AssistClaim` allowed under granted consent; `ViewParchi` denied by `assist-is-not-disclosure`; an ungranted consent authorizes nothing |
| 11 | Verification | `aadesh-verify` runs `run_verify` over the S3 bytes → exit 0, 55 checks; the tamper run → exit 1 |
| 12 | AI explanation | `aadesh-explain` → Bedrock; a contract violation or an unavailable model falls back to deterministic text and is shown as the fallback |

Flows 8, 9 and 10 are the ones that were previously unfalsifiable locally, and they are the
point of D3.

---

## 14. Build sequence

Each step leaves the system coherent and is reported before the next begins.

1. **Adapters + refactor.** `TaskTokenStore` port; DynamoDB, S3, OpenAQ, CloudWatch adapters;
   `AadeshApplication`; LocalStack contract tests; the route-parity guard test. Offline suite
   still green.
2. **First real URL.** CDK `AadeshData` + `AadeshBackend`, corpus synced and checksum-asserted,
   deployed and smoke-tested. Flows 2, 3, 5, 11 reachable.
3. **Identity.** CDK `AadeshIdentity`, JWT authorizer, principal from claims, frontend login.
   Flows 1, 9, 10 become real. Flow 8 splits here and in step 4: the **403 for naming another
   worker** (§6.2) is provable as soon as identity is real, while the happy path needs the
   workflow from step 4.
4. **Workflow.** `workflow` Lambda, ASL timeout fix, the `TaskTokenStore` round trip,
   `SendTaskSuccess` wiring, EventBridge trigger. Flows 6, 7, 8, 12.
5. **Frontend + docs.** Amplify, corpus documentation, README AWS resource table, `.env.example`,
   `make` targets, OpenSearch local, and the recorded evidence for all 12 flows.

---

## 15. Verification strategy

| Layer | Test | Runs |
|---|---|---|
| Adapter contracts | Each DynamoDB / S3 adapter against LocalStack, held to the same contract as its in-memory twin | `make test-aws` |
| Route parity | Local `http.server` skin and API Gateway skin expose the same routes and shapes | `make test` |
| ASL semantics | Step order, `waitForTaskToken`, and now the timeout and reachable `AckTimeout` | `make test` |
| Identity | App client `writeAttributes` excludes both custom attributes; body-supplied `worker_id` is ignored | `make test` |
| Corpus integrity | Uploaded `ChecksumSHA256` equals `manifest.json`'s `sha256`, or the deploy fails | `make sync-corpus` |
| Secrets | No `AKIA`, `aws_secret_access_key`, OpenAQ key or QR secret in the tree | `make test` |
| End-to-end | The 12 flows, executed and recorded | manual, §13 |

The existing 20 invariants in `docs/architecture.md` are re-asserted against the deployed
system rather than assumed to survive it.

---

## 16. Risks and open items

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Root credentials.** The configured identity is `arn:aws:iam::375546530800:root`. Deploying with root is a real security smell | Flagged in the deployment docs; recommend a scoped IAM deploy user. CDK bootstrap requires broad permissions, so this is a documented recommendation rather than something to silently fix |
| R2 | **Bedrock model access.** Claude access must be enabled for the account; a console form may be required and cannot be scripted | Flow 12 degrades to deterministic text by design, and is reported as the fallback rather than as a failure |
| R3 | **`DynamoIdempotencyLedger` is the hardest adapter.** The port promises "compute runs at most once per key, ever, and every later caller receives the first result" — not a conditional `PutItem` | Lease/placeholder record with a conditional write, plus a recovery path when the first caller dies mid-compute. Contract tests cover the crash case explicitly |
| R4 | **OpenAQ response shape drift** could store a reading with the wrong parameter or unit | The provider parses defensively and refuses a reading it cannot attribute to a known parameter, rather than storing a plausible-looking number |
| R5 | **Amplify callback wildcard** (§9.2) is broader than ideal | Documented with the one-line tightening path |
| R6 | **Cold-start corpus materialisation** adds latency on the first request after a deploy | Warm containers skip the re-sync via the `versionId` check; `api` is the only function that needs the corpus |
| R7 | **Cost.** Everything except Bedrock usage and Amplify build minutes is effectively free at this scale | Bedrock spend is bounded by `explain` reserved concurrency; CloudWatch log retention is explicit at 90 days |
| R8 | **First `cdk deploy` includes a Container Image build** on Windows | Docker 28.3.0 is present; the base image is amd64 so no buildx cross-build is needed |

---

## 17. Out of scope

Multi-site, multi-city, a second entity type, claim filing, payment, any real government
integration, a native mobile app, WAF, custom domains, blue/green deploys, and any change to
the deterministic core's decisions. The kill list in the README stands.

---

## 18. What this deployment does not claim

It does not establish a current GRAP invocation (D4). It does not produce an entitlement
amount — the corpus encodes none. It does not show that emissions fell. The public impact
screen keeps its existing `claim_boundary` text, and every count on it stays labelled with its
provenance.
