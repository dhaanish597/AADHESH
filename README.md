# Aadesh (आदेश)

**An environmental compliance execution system for Delhi-NCR construction sites under GRAP
pollution-control restrictions.**

> Aadesh does not claim that AI knows what the law says. It proves that every
> enforcement-relevant decision traces back to an authoritative source, a deterministic rule,
> an authorization decision, and a human acknowledgement.

Three nouns carry the whole product. **Aadesh** is the system. A **Standing Order** is the rule
a supervisor pre-commits to. A **Parchi** (पर्ची) is the slip each worker ends up holding.

---

## The person this is built for

> A construction-site supervisor or labour contractor in Delhi-NCR, who is about to lose a week
> of work to a GRAP halt and does not want to lose their crew with it.

**Beneficiary:** the daily-wage construction worker who loses the day and has an entitlement
nobody has ever documented for them.

**Third principal:** a facilitator — union rep, NGO caseworker, or welfare-board helpdesk
volunteer — who must be able to assist with a claim *without* being handed the worker's full
personal record.

## What Aadesh is not

Not an AQI dashboard. Not an AQI prediction system. Not a chatbot. **Not a government
application and not legal advice.** We do not file claims and we have no access to any welfare
board system. We produce a cited document and a readiness checklist; the claim is filed by the
worker or their facilitator through official channels. Every obligation is a cited starting
point that must be verified against the official CAQM order.

Outputs are phrased as *"this clause applies to your profile"* — never *"you are permitted"* or
*"you will be paid"*.

---

## Current status

The deterministic construction obligation engine and local JSON interface are implemented.
The verified corpus contains **3 official CAQM documents, 8 construction obligations and 4
stage bands**. `make verify` passes **55 citation checks**, including the supporting conditions
and historical invocation/revocation evidence. No entitlement amount is encoded.

There is **no verified current official invocation**. January 2026 Stage III is available only
through explicit historical scenario replay. AQI observations cannot activate a legal stage.
See the [engine API, rule audit and limitations](docs/obligation-engine.md), and the
[initial source audit](docs/corpus-audit.md).

## Quickstart

```bash
make setup           # uv venv + dev deps. No Docker, no AWS account, no network beyond PyPI.
cp .env.example .env
make test            # offline tests, real corpus checks and isolated test doubles
make verify          # re-prove the populated authoritative corpus
make resolve ARGS="--site fixtures/sites/piling-site.json"
make corpus-help     # how to add another authoritative source or cited rule
make api             # local JSON API for the frontend (http://127.0.0.1:8787)
make web             # Next.js frontend (http://localhost:3000), in a second shell
```

| Target | What it does | Needs Docker? |
|---|---|---|
| `make test` | default offline suite | no |
| `make verify` | re-prove every citation against hashed source bytes | no |
| `make verify-tamper` | flip one byte in a scratch copy, prove the check catches it | no |
| `make resolve` | deterministic site resolution, JSON output | no |
| `make corpus` | the ONLY sanctioned way to add a document or a cited clause | no |
| `make api` | local JSON API over the deterministic core, for the frontend | no |
| `make web` | Next.js + TypeScript + Tailwind console over that API | no |
| `make test-integration` | same core against LocalStack | yes |
| `make verify-index` | additionally assert the OpenSearch index agrees | yes |

> `make verify --tamper` is **not** valid GNU make syntax — make parses `--tamper` as one of its
> own options and aborts. Use `make verify-tamper`.

## Frontend

The operational console lives in [`web/`](web/README.md): a Next.js + TypeScript + Tailwind
app whose supervisor screen answers *"what is happening at my site and what do I need to
do?"*. It holds no rules of its own — it calls the local JSON API (`make api`), which is the
same deterministic core the CLI and `make verify` use. It shows the historical Stage III
replay labelled as a replay, the station reading labelled as a synthetic placeholder, and
**no rupee amount**, because the verified corpus establishes none.

---

## Architecture

The resolver and corpus verification run locally today. The cloud and product integrations
below describe the planned architecture.

```
real data → rules-as-data → deterministic resolver → authorization
          → action → human acknowledgement → provenance/verification
```

```
EventBridge (every 15 min)
  └─▶ Lambda: ingest
        ├─ OpenAQ / CPCB nearest-station reading ──▶ DynamoDB (reading + station + ts + staleness)
        └─ S3: hashed CAQM order objects ──▶ OpenSearch (indexed pages, searchable quotes)

Lambda: resolve
  └─ site profile × invoked stage × rules-as-data corpus
        └─▶ obligation set [{status, clause_id, page, quote}]   ◀── pure Python, no model

Step Functions: standing order
  stage trip ─▶ resolve ─▶ Cedar authorize ─▶ open parchi per worker ─▶ PENDING_ACK
             ─▶ QR scanned, worker acknowledges ─▶ parchi sealed ─▶ CloudWatch audit

Bedrock + Strands Agents  ◀── explanation only, contract-checked, deterministic fallback
Cognito ─▶ Next.js on Amplify Hosting   |   Cedar ─▶ every read and write
```

`aadesh_core` is pure Python with **zero AWS imports and zero network access**. Every side
effect crosses a `typing.Protocol` port, so Lambda handlers and the local HTTP server are both
thin adapters over the same core. That is what makes "the same logic runs locally and on AWS"
true rather than aspirational.

**The deterministic system works completely without an LLM.** Bedrock/Strands sits entirely
outside the enforcement path and may only rephrase an already-computed result.

### Two things we refuse to hardcode

**GRAP stage thresholds.** Mapping an AQI reading to a stage requires GRAP's threshold bands,
and those bands live *in the CAQM order*. They are therefore cited corpus data, not constants in
Python. A missing or unproved band cannot establish an implied stage. A guard test fails the
build if an AQI-range integer literal appears in the domain or resolver.

A stage is **invoked by an order**, not computed by arithmetic. CAQM can invoke pre-emptively on
a forecast, or hold off. Aadesh tracks invoked and implied separately and says so when they
diverge.

**Entitlement amounts.** The corpus contains no monetary entitlement. The resolver reports
operational compliance outcomes and clause counts. It cannot generate an amount from worker
counts or application logic, and it makes no measured-emissions claim.

### Three error-handling rules

1. **Unknown remains unknown.** A missing fact needed to decide the result yields `UNKNOWN`.
   Applicability is separate from compliance: `MET`, `NOT_MET`, `UNKNOWN`, `NOT_APPLICABLE`.
2. **Unsourced is a loud state, not an empty one.** A corpus entry whose quote is not verified
   against hashed bytes is excluded from resolution *and reported*. An incomplete corpus
   degrades honestly instead of silently.
3. **Fail closed to deterministic.** Bedrock unavailable, slow, or in breach of its output
   contract → a deterministic sentence is used instead.

Provenance cannot be laundered: `StationReading.provenance` is `MEASURED` | `SYNTHETIC` |
`REPLAY`, and it propagates into every parchi. A synthetic placeholder reading can never be
silently presented as a measured one.

---

## `make verify` — the centrepiece

`make verify` re-hashes every stored source document against the manifest, then re-checks that
every cited quote appears **verbatim** in the page it claims. It also checks the recorded hash
of the extracted page, all supporting rule citations, evidence references and legal literals.
Zero infrastructure, seconds to run on a clean machine.

It checks obligations, entitlements, stage bands **and the invoked stage** — the last of which
is the fact that decides whether any obligation applies at all. A quote is only counted as
proved if the document it was extracted from still hashes to the manifest: extracted text is a
cache of what a document said, and if the bytes have changed, the cache is evidence about
nothing. Without that rule a tampered source would keep enforcing, which is precisely what
verification exists to prevent.

**It currently passes: 3 source documents and 55 citation checks.** Missing or tampered
evidence refuses resolution; setting a rule's verification flag cannot manufacture proof.

`make verify-tamper` flips one byte in a scratch copy and **expects verification to fail**; it
reports `FAILED (expected)` and exits non-zero to show the detection working. If tampered bytes
ever *pass*, it exits with a distinct code and a louder message.

Every source in `corpus/` was downloaded from the official CAQM domain, SHA-256 hashed and
quoted from its recorded page text. The source PDFs remain unchanged. See
[corpus/README.md](corpus/README.md).

The ingestion CLI is the only door in, and it refuses a paraphrase:

```bash
make corpus ARGS="ingest --pdf ~/Downloads/order.pdf --doc-id caqm-grap-2026-01 --url https://caqm.nic.in/..."
make corpus ARGS="add-obligation --file obligation.json"   # quote must be verbatim on the cited page
make verify
```

It calls the **same** normalisation function the verifier calls, so the writer cannot accept
something `make verify` will later reject. A test asserts the two agree, because if they ever
drift apart the central claim of this project is theatre.

---

## Data sources, with honest freshness

| Source | What we get | Real update frequency | Note |
|---|---|---|---|
| OpenAQ | REST API over air quality measurements | point sensors, 5-minute to hourly | our ingestion transport |
| CPCB National AQI | official monitoring network readings | station-level, **hourly** | the authority we cite |
| CAQM GRAP orders | the legal text: stages, thresholds, action lists | by order, irregular | we hash the bytes |
| State BoCW welfare board | worker registration and displacement relief | by notification | we cite, we never assume an amount |

Station data is **hourly**, not real-time, and we say so on screen. The stage comes from an
order, not from our arithmetic.

---

## Scope freeze

**One entity type: `construction_site`.** Frozen on Day 1 and not renegotiated.

### Kill list — do not build

A map as the primary screen · an AQI forecasting model · any computer vision · a second entity
type · multi-city · actual claim filing or payments · integration with any real government
system · hardware · a native mobile app · social features · more than three principal types ·
satellite data bolted on for decoration.

### Cut ladder — decided now, not at 2 AM on Sunday

Cut from the bottom up. **Nothing above the line goes, ever.**

1. Live station ingest with honest timestamps
2. The obligation engine with verbatim citations
3. The worker parchi, with QR handoff and acknowledgement
4. `make verify` and `make verify-tamper`
5. Cedar with the two forbid rules surfacing in the UI
6. The Standing Order pre-commitment
7. Deployed public URL
8. ——— *everything above survives; everything below is expendable* ———
9. Hindi rendering (fall back to English-only before shipping bad Hindi)
10. Facilitator role and the redacted assist view
11. Bedrock/Strands explanation layer (the deterministic text is already correct)
12. Cognito (fall back to a signed role switcher)
13. Parchi PDF export
14. Second entity type

Items 11 and 12 are the ones we will be most reluctant to cut and should be most willing to.
The model adds polish, not correctness. Auth adds realism, not function.

---

## Known weaknesses

**The impact is one step removed from emissions.** Aadesh improves compliance with a rule
designed to clean air; it does not clean air directly. The argument for why that still matters:
GRAP's hardest problem is not knowing when to halt — it is that halting is socially expensive,
so it gets delayed, diluted and lifted early. The displacement is what makes enforcement
politically costly. Pay for the displacement and document it, and the halt becomes cheaper to
enforce and harder to quietly skip.

**It is NCR-only, because GRAP is.** The engine is a rules corpus, so another city is another
corpus.

**Current invocation evidence is absent.** The corpus proves the January invocation was
revoked. It cannot establish a current stage without another verified order. Historical replay
uses the September 2026 schedule as a scenario, because the November 2025 schedule referenced
by the January orders is absent. The page 12 permissions also have an explicitly documented
ambiguity; affected decisions remain `UNKNOWN`.

---

## AWS Deployment

Aadesh deploys to AWS using a service-by-service architecture where every service has a real
responsibility. No service is added merely to increase the service count.

### AWS Resource Inventory

| Resource | Service | Purpose | Responsibility |
|----------|---------|---------|----------------|
| **Amplify Hosting** | Frontend | Next.js app hosting with CI/CD | Serves the Next.js frontend, connects to API Gateway |
| **API Gateway** | API | Single HTTP entry point | Routes requests to Lambda, Cognito authorizer |
| **Lambda Functions** | Compute | Backend handlers | Thin adapters over aadesh_core (11 functions) |
| **DynamoDB Tables** | Database | State persistence | Parchis, readings, standing orders, sites |
| **S3 Bucket** | Storage | Corpus documents | Hashed CAQM order bytes — source of truth |
| **Cognito User Pool** | Identity | User authentication | JWT tokens, role-based access |
| **Cognito Domain** | Identity | Hosted UI (optional) | Sign-in/sign-out pages |
| **Step Functions** | Workflow | Standing Order workflow | Durable workflow with waitForTaskToken |
| **EventBridge** | Events | Scheduled events | Every-15-min AQI ingestion trigger |
| **CloudWatch Logs** | Monitoring | Log aggregation | Lambda logs, Step Functions execution logs |
| **CloudWatch Alarms** | Monitoring | Alerting | Error rate, latency alarms |
| **CloudWatch Dashboard** | Monitoring | Operational view | Unified dashboard for ops |
| **Bedrock** | AI | Explanation (opt-in) | Strands agent for plain-language explanations only |
| **OpenSearch** | Search | Corpus indexing (opt-in) | Searchable citations for verification |

### Detailed Resource Documentation

#### 1. Amplify Hosting (Frontend)

- **Resource**: Amplify App + Branch
- **Purpose**: Host the Next.js frontend with automatic builds on git push
- **Configuration**:
  - Framework: Next.js (auto-detected)
  - Build command: `npm run build`
  - Output directory: `.next`
  - Environment variables: API URL, Cognito config
- **IAM Role**: Amplify service role for S3 build artifacts and CloudFront

#### 2. API Gateway (REST API)

- **Resource**: `AWS::Serverless::Api`
- **Purpose**: Single HTTP entry point for frontend, Cognito authorizer
- **Configuration**:
  - Stage: `{environment}` (dev/staging/prod)
  - CORS: Amplify domains only
  - Auth: Cognito User Pools authorizer (default)
- **Routes**:
  - `/{proxy+}` → API Handler Lambda
  - `/resolve` → Resolve Handler Lambda
  - `/standing-order` → Standing Order Handler Lambda
  - `/parchi/acknowledge` → Parchi Ack Handler Lambda

#### 3. Lambda Functions (Backend)

Sixteen Lambda functions, all Python 3.13, ARM64, 256MB (512MB for Parchi creation):

| Function | Handler | Purpose |
|----------|---------|---------|
| `api_handler` | `aadesh_aws.api_handler.handle` | Main API — supervisor, roster, facilitator, verify, impact |
| `ingest_handler` | `aadesh_aws.ingest_handler.handle` | EventBridge-triggered AQI ingestion |
| `resolve_handler` | `aadesh_aws.resolve_handler.handle` | Pure deterministic obligation resolution |
| `standing_order_handler` | `aadesh_aws.standing_order_handler.handle` | Create/manage Standing Orders |
| `parchi_ack_handler` | `aadesh_aws.parchi_ack_handler.handle` | Worker acknowledges own Parchi |
| `task_waiter` | `aadesh_aws.task_waiter.handle` | Step Functions waitForTaskToken — waits for ack |
| `parchi_creation_handler` | `aadesh_aws.parchi_creation_handler.handle` | Create Parchis for all rostered workers |
| `parchi_seal_handler` | `aadesh_aws.parchi_seal_handler.handle` | Seal acknowledged Parchis over content hash |
| `audit_handler` | `aadesh_aws.audit_handler.handle` | Final audit record for Standing Order execution |
| `stage_trip_handler` | `aadesh_aws.stage_trip_handler.handle` | Determine invoked stage from corpus |
| `parchi_view_handler` | `aadesh_aws.parchi_view_handler.handle` | View Parchi details (for Cedar demo) |

**IAM Policies**: Each Lambda has least-privilege IAM:
- DynamoDB access only to its required tables
- S3 read access only to corpus bucket
- CloudWatch Logs write to its own log group
- Bedrock access (opt-in only, when ExplainBackend=strands_bedrock)
- Step Functions: start/describe execution (for workflow handlers)

#### 4. DynamoDB Tables

| Table | Purpose | Keys | GSIs | PITR |
|-------|---------|------|------|------|
| `parchis` | Parchi persistence | `parchi_id` (PK) | `site_id-index`, `worker_id-index`, `state-index` | Yes (prod) |
| `readings` | AQI readings cache | `station_id` (PK), `observed_at` (SK) | — | No |
| `standing-orders` | Standing Order records | `standing_order_id` (PK) | `site_id-index`, `supervisor_id-index` | Yes (prod) |
| `sites` | Construction site profiles | `site_id` (PK) | — | No |

All tables: PAY_PER_REQUEST billing, AES-256 encryption at rest.

#### 5. S3 Bucket (Corpus)

- **Resource**: `AWS::S3::Bucket`
- **Purpose**: Store hashed CAQM order PDF bytes, keyed by SHA-256
- **Configuration**:
  - Versioning: Enabled
  - Encryption: AES-256 (SSE-S3)
  - Public access: Blocked (all four block settings)
  - Bucket policy: Deny unencrypted transport
- **Contents**: `corpus/sources/*.pdf`, `corpus/sources/*.txt` (extracted page text)

#### 6. Cognito User Pool

- **Resource**: `AWS::Cognito::UserPool`
- **Purpose**: User authentication for frontend
- **Configuration**:
  - Username: email
  - Auto-verified: email
  - MFA: Off (can be enabled for prod)
  - Schema: `role` (String), `assigned_site` (String)
  - Password policy: 12 chars, upper/lower/number/symbol required
- **App Client**: `aadesh-web` — SRP auth, refresh tokens, OAuth code flow
- **Domain**: `{stack-name}-auth` (dev) or custom domain (prod)

#### 7. Step Functions State Machine

- **Resource**: `AWS::Serverless::StateMachine`
- **Purpose**: Durable Standing Order workflow
- **Type**: STANDARD (not Express — needs waitForTaskToken)
- **Workflow**:
  ```
  StageTrip → ResolveObligations → Authorize → CreateParchis → PendingAck
                                                   ↓
                                        (Map: foreach parchi)
                                                   ↓
                                        AwaitWorkerAck (waitForTaskToken)
                                                   ↓
                                        WorkerAcknowledgements → SealParchis → Audit
  ```
- **Logging**: ALL levels to CloudWatch Logs
- **Tracing**: X-Ray enabled

#### 8. EventBridge Rules

| Rule | Schedule/Event | Target | Purpose |
|------|---------------|--------|---------|
| `standing-order-events` | `aadesh.events` → `StageInvocation` | Step Functions | Trigger workflow when stage invoked |
| `IngestHandler.Every15Minutes` | rate(15 minutes) | Ingest Lambda | Scheduled AQI ingestion |

#### 9. CloudWatch

**Log Groups**:
- `/aws/lambda/{stack}-api`
- `/aws/lambda/{stack}-ingest`
- `/aws/lambda/{stack}-resolve`
- `/aws/lambda/{stack}-standing-order`
- `/aws/lambda/{stack}-parchi-ack`
- `/aws/lambda/{stack}-task-waiter`
- `/aws/lambda/{stack}-create-parchis`
- `/aws/lambda/{stack}-seal-parchis`
- `/aws/lambda/{stack}-audit`
- `/aws/lambda/{stack}-stage-trip`
- `/aws/states/{stack}-standing-order`

**Alarms**:
- `ApiErrorsAlarm`: API Lambda errors > 5 in 5 minutes
- `LambdaDurationAlarm`: API Lambda p95 > 25s for 3 periods

**Dashboard**: Unified dashboard with API errors, Lambda metrics, SFN logs, DynamoDB throughput

#### 10. Bedrock (opt-in)

- **Purpose**: AI explanations only, outside enforcement path
- **Configuration**:
  - Model: `amazon.nova-lite-v1` or `anthropic.claude-sonnet-4-5-20250827-v1`
  - Temperature: 0.1 (explanation should be deterministic)
  - Max tokens: 1024
- **IAM**: Bedrock `InvokeModel` on specific models only
- **Fallback**: Always falls back to deterministic explanation on any failure

#### 11. OpenSearch (opt-in)

- **Resource**: `AWS::OpenSearchService::Domain`
- **Purpose**: Indexed corpus pages for search-backed verification
- **Configuration**:
  - Engine: OpenSearch 2.11
  - Instance: t3.small.search (1 node)
  - Encryption: At rest + node-to-node
  - HTTPS enforced, TLS 1.2 minimum
  - Access: Lambda execution role only
- **IAM**: `es:ESHttp*` on domain ARN only

### Infrastructure as Code

All AWS resources are defined in:

```
infra/aws/
├── template.yaml          # SAM template — all resources
├── README.md             # Deployment documentation
├── LOCAL_DEV.md          # Local development with LocalStack
└── stepfunctions/
    └── standing-order.asl.json  # Step Functions workflow definition
```

### Deployment Commands

```bash
# Build and deploy backend
cd infra/aws
sam build --use-container
sam deploy --guided

# Deploy frontend to Amplify
cd web
amplify init
amplify add hosting
amplify publish
```

### Environment Variables

All environment variables are documented in [.env.example](../.env.example).

Production secrets must be stored in:
- **AWS Secrets Manager**: QR signing key, API keys
- **SSM Parameter Store**: Non-sensitive configuration

### Deployment Documentation

Full deployment guide: [infra/aws/README.md](infra/aws/README.md)
Local development guide: [infra/aws/LOCAL_DEV.md](infra/aws/LOCAL_DEV.md)

---

## Licence and attributions

Apache-2.0. See [LICENSE](LICENSE).

Dependencies: [`cedarpy`](https://pypi.org/project/cedarpy/) (Python bindings to AWS's
open-source Cedar policy engine), `jsonschema`, `pytest`, `ruff`.

**AI tooling disclosure:** Claude Code (Anthropic) was used for architecture review,
scaffolding and test authoring.
