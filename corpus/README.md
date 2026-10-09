# Corpus — rules as data, with provenance

The corpus contains **3 official CAQM source documents, 8 construction obligations, 4 stage
bands and the January 2026 invocation/revocation**. `make verify` re-proves 55 citations. The
entitlement list is empty. There is no verified current invocation.

See the [deterministic rule audit and API](../docs/obligation-engine.md) for every condition,
exception and unresolved wording, and the [initial source audit](../docs/corpus-audit.md) for
the official URLs and original primary citations.

## The rule that governs this directory

> Do not encode GRAP thresholds, action lists, or entitlement amounts from memory, from a
> strategy document, or from a news article.

GRAP has been revised repeatedly, with orders amending earlier orders. For every measure you
intend to encode, you must locate the **current** CAQM order, download it from the official
domain, hash the bytes, and encode only from the text you are holding.

Do not treat historical or uncertain evidence as current. Preserve cited clauses and model
their conditions faithfully; unresolved wording must remain explicitly unknown. The engine
audit corrects the initial one-fact approximations without deleting any of the eight rules.

## Layout

```
corpus/
├── sources/
│   ├── manifest.json             Provenance: doc_id, PDF/page hashes, official URL, retrieved_at
│   ├── <doc_id>.pdf              The EXACT downloaded bytes. Committed on purpose: it is
│   │                             what makes `make verify` reproducible for a judge.
│   └── pages/<doc_id>/p<N>.txt   Extracted per-page text. Quotes are checked against these.
├── obligations/construction_site.json
├── entitlements/cess_fund.json
├── stage_bands/grap_stage_bands.json   AQI→stage thresholds. THE ONLY place they may exist.
└── invoked_stage.json            Which stage a CAQM ORDER has invoked (not computed from AQI).
```

The JSON Schemas live with the code, in `services/aadesh_core/corpus_schemas/`, not here.
That is deliberate: a corpus directory that shipped its own schema could weaken its own
validation, which is the same self-certifying problem as a corpus entry declaring itself
verified. Both are refused.

## Adding a document

Use the ingestion CLI for new documents and clauses; it refuses a quote that is not on the
page it claims. `make corpus-help` lists the commands. Model corrections to existing rules
must preserve the original evidence, add tests and be documented in the engine audit.

```bash
# 1-4. hash the bytes you downloaded, store them, extract page text. One command.
make corpus ARGS="ingest --pdf ~/Downloads/order.pdf --doc-id caqm-grap-2026-01"
make corpus ARGS="ingest ... --url https://caqm.nic.in/... --publisher CAQM"

# 5. add a clause, quoting VERBATIM from one of the p<N>.txt files it just wrote
make corpus ARGS="add-obligation --file obligation.json"
make corpus ARGS="add-entitlement --file entitlement.json"
make corpus ARGS="add-stage-band --file band.json"
make corpus ARGS="invoke-stage --stage 3 --doc-id caqm-grap-2026-01 --page 2"
make corpus ARGS="invoke-stage ... --quote '<the sentence on page 2 that invokes Stage III>'"

# 6. re-prove every citation against the stored bytes
make verify
```

The CLI and `make verify` call **the same** `normalise` function, so the writer cannot accept
something the verifier will reject. If those two ever drift apart, the central claim of this
project is theatre -- so a test asserts they agree.

What the CLI refuses, and why:

| Refusal | Why it exists |
|---|---|
| bytes that are not a PDF | a saved HTML page or your own summary is not the order |
| a PDF with no text layer | a quote cannot be proved against pixels; OCR it first and say you did |
| a `doc_id` already in the manifest | re-ingesting would orphan every citation checked against the old bytes |
| a `doc_id` with a slash or a space | it becomes a filename; traversal writes outside the corpus |
| a **paraphrased** quote | the single most important refusal here |
| a quote on the wrong page | a right sentence attributed to the wrong page is still a false citation |
| an entry declaring its own `source_state` | provenance is computed, never asserted |
| an amount whose own quote is unfound | a rupee figure with nothing behind it is the failure mode of this whole domain |
| a citation to a document nobody ingested | it could never be re-proved, so it is not a citation |
| an id that already exists | editing a clause in place would desynchronise it from parchis already issued |
| an invoked stage with no citation | it decides which obligations apply, so it is the last thing that may be taken on trust |

## Two mechanisms that are easy to confuse

- `ingest` **never** populates an obligation, threshold or amount. It only stores bytes and
  extracts text. It cannot encode a rule, by construction.
- `add-*` **never** invents a hash or a page. Every citation is checked against page text
  that `ingest` produced from bytes that were hashed at the moment of download.

## The invoked stage is a citation too

`invoked_stage.json` is the fact that decides whether **any** obligation applies. It therefore
carries the same `source_doc` / `page` / `quote` every other citation carries -- the same key
names, so generic verification can find it without a special case -- and `make verify`
re-proves it like the rest.

The loader **refuses** an invoked stage it cannot re-prove rather than returning `None`.
Returning `None` would read as "no stage is invoked" and silently drop every obligation in the
corpus, which is the opposite of failing safe.

## Why `quote` must be verbatim

`make verify` checks the PDF and extracted-page hashes and asserts the `quote` string appears
in that recorded page text. Supporting quotes for conditions and exceptions are verified too.
A paraphrase — however faithful — fails. This is deliberate: it is the mechanism that stops
good intentions from degrading into remembered law under deadline pressure.

## Two concepts that are never conflated

- **Invoked stage** — set by a CAQM *order*. Carries the order's `doc_id` and `sha256`.
- **Implied stage** — derived from a station reading via the cited `stage_bands`.

A stage is invoked by an order, not computed by arithmetic. CAQM can invoke pre-emptively on a
forecast, or hold off. When invoked and implied diverge, Aadesh says so explicitly rather than
quietly preferring one.

The four bands come from the September 2026 schedule. Stage IV's strict lower boundary is
explicit data (`aqi_lower_inclusive: false`); thresholds and inclusivity must agree with their
quotes. No observation creates an official invocation.

January Stage III was revoked on January 22 and is available only in explicit replay mode.
The historical orders refer to a different schedule revision, so that replay is labelled a
scenario using the available rules, not proof of the obligations in force in January.

## Rule representation

Each obligation separates factual `applicability` from its compliance `requirement`. Predicate
trees use only `eq`, `gte`, `in`, `not_in`, `and`, `or`; every node names supporting evidence.
Stage activation, continuation and the required action also name evidence. An original primary
citation remains attached to every row. The small fact vocabulary is listed in the
[engine documentation](../docs/obligation-engine.md#scope-of-a-site-profile).

## Amounts

No held source establishes an entitlement amount, so none is encoded. The resolver produces
operational compliance outcomes only. Worker-count arithmetic cannot create a legal obligation
or a monetary figure, and clause counts are not measurements of pollution prevented.
