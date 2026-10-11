# Aadesh v2 — Foundation Design

**Date:** 2026-10-08 (Day 1 of Environmental Hacks, Bharat Builds Tour)
**Status:** Approved. Scope is the engineering foundation plus one vertical slice. Not the full application.

---

## 1. What Aadesh is

A pollution-control **execution layer**. It converts an officially invoked GRAP stage into
site-specific obligations for **one** construction site, and produces a provable worker record
when the environmental restriction displaces work.

**The thesis, stated as a falsifiable claim:**

> Aadesh does not claim that AI knows what the law says. It proves that every
> enforcement-relevant decision traces back to an authoritative source, a deterministic rule,
> an authorization decision, and a human acknowledgement.

Aadesh is **not**: an AQI dashboard, an AQI prediction system, a chatbot, a government
application, legal advice, a claim-filing system, or a payment system.

**Entity scope: `construction_site` only.** One entity type. No schools, factories, or other cities.

## 2. Non-negotiable principle

```
real data → rules-as-data → deterministic resolver → authorization
          → action → human acknowledgement → provenance/verification
```

The deterministic system works **completely without an LLM**. Bedrock/Strands sits entirely
outside the enforcement path and may only explain already-computed results.

## 3. Architecture — ports and adapters

`aadesh_core` is pure Python with **zero AWS imports and zero network access**. Every side
effect crosses a `typing.Protocol` port. Lambda handlers and the local HTTP server are both
thin adapters over the same core. That is what makes "same logic locally and on AWS" true
rather than aspirational.

| Port | Purpose | Adapters |
|---|---|---|
| `Clock` | injected time; no `now()` in domain | `SystemClock`, `FrozenClock` |
| `AqiProvider` | station reading + staleness + provenance | `Fixture` (now), `OpenAQ`, `Replay` |
| `SourceDocumentStore` | hashed order bytes + extracted page text | `LocalFile`, `S3` |
| `RulesCorpus` | obligations, entitlements, stage bands | `LocalFileJson` |
| `InvokedStageSource` | stage from an **order**, with its hash | `LocalFile`, `DynamoDB` |
| `ObligationResolver` | site × stage × corpus → results | `Deterministic` only |
| `AuthorizationProvider` | Cedar decision + policy `@id` | `Cedar`, `AllowAllTestOnly` |
| `ParchiStore` | lifecycle persistence | `InMemory`, `DynamoDB` |
| `CitationVerifier` | re-prove quotes against source bytes | `SourceBytes`, `OpenSearchIndex` |
| `ExplanationProvider` | contract-checked prose | `Deterministic`, `StrandsBedrock` |
| `AuditLog` | append-only decision record | `Stdout`, `CloudWatch` |

## 4. Two design resolutions that shape the data model

### 4.1 The implied GRAP stage is corpus data, never code

Mapping an AQI reading to a stage requires GRAP's threshold bands, and those bands live **in the
CAQM order**. They are therefore cited corpus data exactly like obligations, not constants in
Python. Until a real order is hashed and cited, the implied stage resolves to `UNKNOWN` and the
status line says so.

A guard test enforces this: no integer literal in the AQI band range may appear anywhere in
`aadesh_core/domain` or `aadesh_core/resolver`.

Two separate concepts, never conflated:

- **`InvokedStage`** — comes from a CAQM order. Carries `order_doc_id`, `order_sha256`, `invoked_at`.
- **`ImpliedStage`** — derived from a reading via cited stage bands. Carries the citation.

When the two diverge, `StageStatus.divergent` is true and the UI must say so explicitly.

### 4.2 Entitlement amounts are optional and citation-backed

`Entitlement.amount` is `None` unless populated from a cited source. The headline counter
renders rupees **only if** every contributing clause carries a cited amount; otherwise it renders
**displaced worker-days**, which is always provable. Both shapes are first-class from day one.

A guard test enforces this: no currency symbol and no money-named numeric constant in `aadesh_core`.

## 5. Three error-handling rules

1. **Tri-state, never inferred false.** A missing or explicitly unknown site fact yields
   `ObligationStatus.UNKNOWN`, never `NOT_MET`.
2. **Unsourced is a loud state, not an empty one.** A corpus entry whose quote is not verified
   against hashed source bytes is `UNSOURCED`, is **excluded from resolution**, and is reported
   in `ObligationSet.excluded_unsourced`. An incomplete corpus degrades honestly.
3. **Fail closed to deterministic.** If Bedrock is unavailable, slow, or violates the output
   contract, a deterministic sentence is used. The contract rejects unknown clause ids,
   obligations the engine never computed, and the words *approved* / *guaranteed* /
   *legal advice*.

### 5.1 Provenance cannot be laundered

`StationReading.provenance` is required: `MEASURED` | `SYNTHETIC` | `REPLAY`. Provenance
propagates into `ObligationSet` and into every `Parchi`. A synthetic placeholder reading can
therefore never be silently presented as a measured one. Enforced by test.

## 6. Parchi lifecycle

```
DRAFT ──open──▶ PENDING_ACK ──acknowledge──▶ SEALED (terminal, immutable)
  │                   │
  └────────void───────┴──▶ VOID (terminal)
```

- Only the worker named on the parchi may acknowledge it. Enforced by Cedar
  (`@id("no-proxy-acknowledgement")`), not by application code.
- `SEALED` computes a content hash and is append-only. No transition leaves `SEALED` or `VOID`.
- Any illegal transition raises `IllegalParchiTransition`.

## 7. Cedar

Real Cedar 4.x via the `cedarpy` native binding, evaluated in-process from `.cedar` files.
Verified on 2026-10-08: `cp313-win_amd64` wheel installs, `is_authorized` evaluates `forbid`
correctly.

**Implementation note.** `diagnostics.reasons` returns positional policy ids (`policy0`,
`policy1`), **not** the `@id` annotation. The adapter builds a positional-id → annotation map at
load time via `policies_to_json_str`, then maps a denial to its human sentence from
`infra/cedar/denials.json`. Without this step the plan's "`@id` turns a denial into a sentence"
does not actually work.

`AllowAllTestOnly` is named to be embarrassing on purpose and refuses to construct when
`AADESH_ENV != "test"`.

## 8. `make verify` — the centrepiece

Zero-infra by default: re-hashes stored order bytes against the source manifest and re-checks
that every cited quote appears **verbatim** in the page it claims. No Docker, seconds to run on
a judge's clean machine.

| Command | Meaning |
|---|---|
| `make verify` | core proof. Exit non-zero on any hash mismatch, missing quote, or **zero verified citations** |
| `make verify --tamper` | flips one byte in a scratch copy; **must** exit non-zero |
| `make verify --with-index` | additionally asserts the OpenSearch index agrees. Needs Docker |

**`make verify` ships failing.** With an empty corpus it reports zero verified citations and
exits 2 with an explicit, actionable message. This is not a defect — it is the gate that makes
paraphrasing fail loudly from Day 1.

## 9. Corpus — deliberately empty

`corpus/` ships with JSON Schemas and **empty** data files. No GRAP threshold, obligation,
action list, or rupee amount is populated until the authoritative CAQM order is located,
downloaded from its official domain, SHA-256 hashed, and quoted verbatim.

Standing rule from the plan: **if you cannot establish which order is current for a measure,
drop that measure.** Ten certain obligations beat twenty-five uncertain ones. A confidently
wrong citation is worse than no citation, because provenance has been loudly advertised.

## 10. Testing

Default `make test` is pure `pytest` against in-memory fakes — no Docker, ~seconds.
`make test-integration` runs the same core against LocalStack.

Shared **contract test suites per port** run against fake *and* real adapters, so the DynamoDB
adapter is held to the same behaviour as the in-memory one.

Credibility invariants, tested first:

| Invariant | Test |
|---|---|
| missing fact → `UNKNOWN`, never `NOT_MET` | `test_resolver_tristate.py` |
| unsourced clause cannot enter resolution | `test_resolver_unsourced.py` |
| no hardcoded GRAP threshold in domain/resolver | `test_no_hardcoded_legal_data.py` |
| no hardcoded rupee entitlement | `test_no_hardcoded_legal_data.py` |
| the guard itself can detect a violation | `test_source_scan_guard.py` |
| `AllowAllTestOnly` cannot load outside test | `test_test_only_adapter_guard.py` |
| Cedar forbid rules enforced, with `@id` | `test_cedar_policies.py` |
| illegal parchi transitions fail | `test_parchi_lifecycle.py` |
| contract rejects unsupported claims | `test_explanation_contract.py` |
| synthetic provenance propagates to parchi | `test_provenance_propagation.py` |
| empty corpus → `make verify` exits non-zero | `test_verify_cli.py` |
| tampered source → `--tamper` exits non-zero | `test_verify_cli.py` |

The guard tests are proven able to fail by unit-testing the pure scanner against a known-bad
fixture string — the same philosophy as `--tamper`. A guard that has never failed proves nothing.

## 11. Out of scope for this foundation

Deferred, in cut-ladder order: deployed public URL, Step Functions wiring beyond a skeleton,
Cognito, QR issuance and the worker scan flow, Next.js screens beyond a skeleton, Hindi
rendering, the facilitator redacted view, Bedrock/Strands adapter, OpenSearch index adapter,
parchi PDF export.

Never in scope: a second entity type, multi-city, AQI forecasting, computer vision, maps as a
primary screen, real claim filing, payments, or any government system integration.

## 12. Known blockers carried forward

- **Authoritative CAQM order not yet located.** Blocks the entire corpus. Highest priority
  non-engineering task.
- **SAM CLI not installed** on the dev machine. Blocks `sam local`; does not block the core slice.
- **Submission close time is contradictory** between the two source docs (8:00 AM vs 8:00 PM on
  11 Oct). Must be confirmed on the schedule page and Discord.

---

## 13. Addendum — 2026-10-08, written after implementation

Four things changed while building the ingestion mechanism. Sections 1-12 above are left as
approved; this records the deltas and why each was necessary.

### 13.1 There is now one door into the corpus

`aadesh-corpus` (aliased as `make corpus`) is the only sanctioned way to add a source document
or a cited clause. `ingest` hashes the bytes you downloaded, stores them, extracts per-page
text, and records the official URL and retrieval time. `add-obligation`, `add-entitlement`,
`add-stage-band` and `invoke-stage` accept a clause **only** if its `quote` is found on the page
it cites.

The quote check and `make verify` call the same function. That is the load-bearing detail: a
writer more lenient than the verifier would admit entries the gate later rejects, and a writer
stricter than it would reject sound entries. `normalise` was promoted from a private helper in
`verifier.py` to the public verification API for exactly this reason, and a test asserts that an
entry the CLI accepts is an entry `make verify` proves.

### 13.2 The invoked stage was outside the proof. It is not now.

`invoked_stage.json` decides whether **any** obligation applies. Until now it was the one legal
claim in the corpus that nothing re-proved: the loader checked only that the named order was in
the manifest, never that the stage's own sentence existed anywhere.

It is now a citation like every other — `source_doc`, `page`, `quote`, the same key names, so
generic verification finds it without a special case — and it has a schema
(`corpus_schemas/invoked_stage.schema.json`). `order_doc_id` was renamed to `source_doc`; the
loader refuses the old key with a pointer to the new one rather than ignoring the field and
leaving the stage silently unverified.

The loader **refuses** an invoked stage it cannot re-prove. It does not degrade to `None`:
`None` reads as "no stage is invoked" and would drop every obligation in the corpus, which is
the opposite of failing safe.

### 13.3 A citation is only proved if its document still hashes

Extracted page text is a cache of what a document said. If the document's bytes no longer hash
to the manifest, a quote found in that cache proves nothing about anything — yet
`verified_entry_ids` previously counted it. A tampered PDF with intact page text still produced
`VERIFIED` obligations at runtime, which is precisely the failure verification exists to
prevent.

A citation now fails when the document it names fails its hash check. Consequence: a tampered
source makes every entry citing it `UNSOURCED`, the resolver excludes them, and
`fully_sourced` is false. The gate is enforced at runtime, not only in the CLI report.

### 13.4 What this does not change

No GRAP threshold, obligation, action list or rupee amount was encoded. The corpus is still
empty in every list. `make verify` still exits 2 (`CORPUS_NOT_READY`), which remains the
correct Day 1 state: the mechanism is now complete and the data is still absent, and that
distinction is the whole point.
