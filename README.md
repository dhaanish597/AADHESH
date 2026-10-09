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

AQI ingestion, deployed workflows, Standing Orders, worker Parchis, model integrations and the
frontend remain subsequent work. The foundation's test slice is not a finished application.

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

## Licence and attributions

Apache-2.0. See [LICENSE](LICENSE).

Dependencies: [`cedarpy`](https://pypi.org/project/cedarpy/) (Python bindings to AWS's
open-source Cedar policy engine), `jsonschema`, `pytest`, `ruff`.

**AI tooling disclosure:** Claude Code (Anthropic) was used for architecture review,
scaffolding and test authoring.
