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

## Current status — foundation only

This repository currently contains the engineering foundation and one vertical slice that
proves the architecture end to end. It is **not** the finished application. See
[the foundation spec](docs/superpowers/specs/2026-10-08-aadesh-v2-foundation-design.md) for what
is deliberately deferred.

**`make verify` currently fails, on purpose.** See [below](#make-verify--the-centrepiece).

## Quickstart

```bash
make setup           # uv venv + dev deps. No Docker, no AWS account, no network beyond PyPI.
cp .env.example .env
make test            # pure pytest against in-memory fakes, ~seconds
make verify          # citation proof. Exits non-zero until the corpus is sourced.
```

| Target | What it does | Needs Docker? |
|---|---|---|
| `make test` | default suite, fakes only | no |
| `make verify` | re-prove every citation against hashed source bytes | no |
| `make verify-tamper` | flip one byte in a scratch copy, prove the check catches it | no |
| `make test-integration` | same core against LocalStack | yes |
| `make verify-index` | additionally assert the OpenSearch index agrees | yes |

> `make verify --tamper` is **not** valid GNU make syntax — make parses `--tamper` as one of its
> own options and aborts. Use `make verify-tamper`.

---

## Architecture

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
Python. Until a real order is hashed, the implied stage is `UNKNOWN`. A guard test fails the
build if an AQI-range integer literal appears in the domain or resolver.

A stage is **invoked by an order**, not computed by arithmetic. CAQM can invoke pre-emptively on
a forecast, or hold off. Aadesh tracks invoked and implied separately and says so when they
diverge.

**Entitlement amounts.** `entitlement.amount` is `null` unless a figure appears in a hashed
source document carrying its own citation. When null, Aadesh reports **displaced worker-days**,
which is always provable. The headline counter renders rupees only if every contributing clause
has a cited amount.

### Three error-handling rules

1. **Tri-state, never inferred false.** A missing site fact yields `UNKNOWN`, never `NOT_MET`.
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
every cited quote appears **verbatim** in the page it claims. Zero infrastructure, seconds to
run on a clean machine.

**It currently exits non-zero because the corpus has zero verified citations.** That is the
expected Day 1 state and the gate working as designed — not a defect. A hash check that has
never failed proves only that you did not delete your files.

`make verify-tamper` flips one byte in a scratch copy and **expects verification to fail**; it
reports `FAILED (expected)` and exits non-zero to show the detection working. If tampered bytes
ever *pass*, it exits with a distinct code and a louder message.

Nothing in `corpus/` is populated until the authoritative CAQM order is located, downloaded
from its official domain, SHA-256 hashed, and quoted verbatim. See [corpus/README.md](corpus/README.md).

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

**No authoritative CAQM source is encoded yet.** This is the top blocker. Until it is resolved,
`make verify` fails and no obligation can enter resolution.

## Licence and attributions

Apache-2.0. See [LICENSE](LICENSE).

Dependencies: [`cedarpy`](https://pypi.org/project/cedarpy/) (Python bindings to AWS's
open-source Cedar policy engine), `jsonschema`, `pytest`, `ruff`.

**AI tooling disclosure:** Claude Code (Anthropic) was used for architecture review,
scaffolding and test authoring.
