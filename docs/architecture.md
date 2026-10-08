# Aadesh — architecture

Companion to the [foundation spec](superpowers/specs/2026-10-08-aadesh-v2-foundation-design.md).
This document covers the shape of the system and the AWS resources planned. The spec covers
why the decisions were made.

## The chain

```
real data → rules-as-data → deterministic resolver → authorization
          → action → human acknowledgement → provenance/verification
```

Each arrow is a boundary something could be faked across, and each has a test that says it
cannot be.

## Ports and adapters

`aadesh_core` is pure Python: **zero AWS imports, zero network, zero clock reads**. Every side
effect crosses a `typing.Protocol` port in `aadesh_core/ports/`.

```
services/
├── aadesh_core/          ← pure. imports nothing but stdlib + jsonschema types
│   ├── domain/           value objects, enums, the UNKNOWN_FACT sentinel
│   ├── ports/            8 Protocols: the only way out
│   ├── resolver/         site × stage × corpus → ObligationSet   (pure function)
│   ├── parchi.py         DRAFT → PENDING_ACK → SEALED            (pure transitions)
│   ├── stages.py         invoked vs implied, from cited bands only
│   ├── verification/     re-prove citations against hashed bytes
│   ├── explanation/      the output contract + deterministic text
│   └── corpus_schemas/   JSON Schemas (with the CODE, not the corpus)
├── aadesh_adapters/      ← everything that touches the world
└── aadesh_cli/           make verify
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
`aadesh_core.explanation.check_explanation` before a user sees it. **The model can be entirely
unavailable and Aadesh still works.**

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

## Known gaps

- **No authoritative CAQM source is encoded.** The corpus is empty and `make verify` fails.
  This is the top blocker and it is not an engineering one.
- **SAM CLI is not installed** on the current dev machine, so `sam local` is untested.
- **AWS adapters are not written** beyond the ports they will satisfy. Deliberate: the core
  slice had to work locally first.
