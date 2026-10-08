# Aadesh — the explanation layer (Bedrock + Strands)

> **AI explains; deterministic code decides.**

This document is the contract for the optional model layer. It is deliberately short, because
the layer is deliberately thin. Everything a user is *entitled* to see is produced without a
model; the model only rephrases it.

## The shape

```
AUTHORITATIVE CAQM SOURCE
        ↓
DETERMINISTIC CORE            (verify → resolve → authorize → parchi → ack → seal)
        ↓
VERIFIED FACTS / OBLIGATIONS  (ResolutionResult, Parchi — authoritative, retained separately)
        ↓
ExplanationRequest            (structured, PII-free, deterministic)
        ↓
BEDROCK / STRANDS             (optional; no tools, no authority)
        ↓
ExplanationResponse           (grounded, contract-checked, presentation-only)
        ↓
HUMAN-READABLE EXPLANATION
        ↓ fallback on any failure
DETERMINISTIC TEXT            (always correct, always available)
```

Never:

```
CAQM → LLM → legal decision
```

## Components

| Module | Responsibility |
|---|---|
| `aadesh_core/explanation/contract.py` | The output contract: banned decision-register phrases, uncited money, and structured claims that must not contradict the resolver. |
| `aadesh_core/explanation/context.py` | `ExplanationRequest` — the structured, PII-free input. Builders `request_for_resolution` / `request_for_parchi`. |
| `aadesh_core/explanation/response.py` | `ExplanationResponse` — the strict structured output and its parser. |
| `aadesh_core/explanation/grounding.py` | Citation/stage/replay grounding: refuses anything the model was not given. |
| `aadesh_core/explanation/prompt.py` | The strict system prompt and payload embedding. Deterministic, testable offline. |
| `aadesh_core/explanation/service.py` | `ExplanationService` — authorize, render, check, fall back. |
| `aadesh_core/ports/explanation.py` | `ExplanationModel` protocol (and the original `ExplanationProvider`). |
| `aadesh_adapters/explain/bedrock.py` | Amazon Bedrock adapter (boto3 imported lazily, client injectable). |
| `aadesh_adapters/explain/strands.py` | Strands adapter — a tool-free, read-only agent wrapper. |
| `aadesh_adapters/explain/fake.py` | `FakeExplanationModel` — deterministic, offline, test-only. |

The dependency direction is **adapters → core**. Nothing in `aadesh_core` imports Bedrock,
Strands, boto3, or an adapter. `tests/unit/test_explanation_no_model.py` enforces this.

## Model authority: there is none

The deterministic result is a separate object from the model's response and is never replaced
by it. `ExplanationOutcome` carries both:

* `outcome.prompt_request` / `outcome.deterministic` — authoritative, unchanged.
* `outcome.explanation` — presentation only; equal to the model's prose only when
  `status is AVAILABLE`.

If the model disagrees with the engine, **the deterministic result wins**. The model cannot
overwrite `official_stage`, `implied_stage`, obligation status, authorization, Parchi state,
source hash, or source citation: it has no field for them, and any echo that differs is caught
by grounding and rejected.

## The `ExplanationRequest` schema (`explanation/1`)

```
context_id        opaque, deterministic (expl-<kind>-<ref>)
kind              obligation | stage | aqi_discrepancy | historical_replay | parchi | unknown_fact
question          optional natural-language question
site_ref          opaque site id
replay_status     CURRENT | REPLAY          (must be echoed)
official_stage    display string, e.g. "Stage III"  (must be echoed)
implied_stage     display string or "NONE"          (must be echoed)
stage_agreement   ALIGNED | DISCREPANCY | OFFICIAL_ONLY | NO_OFFICIAL_INVOCATION
stage_reason      the engine's own sentence
replay_notice     present for a replay
reading_provenance measured | synthetic | replay
obligations[]     {obligation_id, label, status, applicable, required_action, reason}
facts[]           {name, value, known}     (known=false is UNKNOWN)
citations[]       {source_doc, page, quote, label, source_hash}
parchi_ref        opaque Parchi id (parchi explanations only)
parchi_status     lifecycle state (parchi explanations only)
has_cited_amount  whether a cited entitlement amount exists
```

`to_prompt_payload()` is the **only** thing sent to the model.

### Privacy boundary

The request never carries `Aadhaar`, phone, bank account, PAN, home address, a raw QR token, or
unnecessary worker personal data. In particular a Parchi explanation carries the Parchi's opaque
reference and state — **not** the worker's id. `tests/unit/test_explanation_privacy.py` asserts
these terms cannot appear in a payload, a prompt, or an audit record. The AI layer is not a
backdoor to `ViewParchi`.

## Citation grounding

The model is supplied citations (source doc, page, verified quote, source hash, and the
obligation/action they support). It may only reference those. `check_grounding` returns an
`UnsupportedReference` for:

* an **unknown citation** — a doc/page not supplied;
* an **invented source hash** — a hash that is not supplied, whether in a structured reference
  or in the prose;
* a **stage contradiction** — an echoed official/implied stage that differs from the engine's;
* a **replay contradiction** — a replay presented as current.

The original deterministic citation is preserved independently of the model response. A
response that contains an unsupported reference is marked `UNSUPPORTED` and the deterministic
text is shown — it is never silently accepted.

## Output contract

`check_explanation` (and the prose-only `check_prose`) additionally reject decision-register
phrasing (`approved`, `guaranteed`, `legal advice`, `you will be paid`, …) and monetary figures
when no cited amount exists. Structured claims that name an unknown clause or contradict the
resolver's computed status are rejected as well. The model is never asked a legal question such
as "which stage should apply" — it is only asked to *explain* a result the engine already
reached.

## Authorization boundary

```
Principal → Cedar authorization → allowed explanation context → Bedrock/Strands → explanation
```

`ExplanationService` requires:

* **site explanations** — `ViewSiteExecution` on the site;
* **Parchi explanations** — `ViewParchi` on the Parchi.

Authorization happens **first**. On a denial `AuthorizationDenied` is raised before any
protected data is gathered, and the model is **never called**. A facilitator who may
`AssistClaim` but not `ViewParchi` gets exactly that refusal; there is no path from the
explanation endpoint around Cedar.

## Strands boundary

If Strands is used it is an orchestration/explanation wrapper only. The agent is constructed
with **no tools**. It cannot trigger a Standing Order, issue a halt, create/acknowledge/seal a
Parchi, authorize a principal, modify CAQM source data, or modify resolver rules. `tests/unit/
test_explanation_no_model.py` asserts the adapters import no module that could mutate compliance
state.

If Strands (or boto3) is not installed, `from_strands()` / `BedrockExplanationModel()` raise
`ExplanationUnavailable` and the caller falls back to deterministic text. The rest of Aadesh does
not depend on either.

## Failure behavior

If Bedrock is unavailable, Aadesh still works:

* `status = EXPLANATION_UNAVAILABLE`;
* the deterministic explanation is shown;
* compliance resolution, authorization, obligation status, and Parchi state are unchanged;
* there is no infinite retry and no fabricated explanation.

A response that breaches grounding or the contract yields `status = UNSUPPORTED` (with the
specific `violations` / `unsupported` recorded) and the deterministic text. Neither state is an
error the user must resolve.

## Audit

When configured, explanation requests are recorded with an opaque reference only:

```
event         ExplanationRequested
detail        explanation_id, kind, site_ref, parchi_ref, model, outcome, detail
```

No raw worker PII, raw QR token, secret, or full prompt is logged. The audit record is not a PII
leak.

## Tests

* `tests/unit/test_explanation_context.py` — context schema and PII-free payload.
* `tests/unit/test_explanation_grounding.py` — hallucinated citations/hashes/stages/replay.
* `tests/unit/test_explanation_service.py` — availability, fallback, audit.
* `tests/unit/test_explanation_authorization.py` — Cedar enforcement, no model call on denial.
* `tests/unit/test_explanation_security.py` — the 15 security properties.
* `tests/unit/test_explanation_types.py` — the six explanation scenarios.
* `tests/unit/test_explanation_adapters.py` — Bedrock/Strands/fake, all offline.
* `tests/unit/test_explanation_privacy.py` — privacy boundaries.
* `tests/unit/test_explanation_no_model.py` — static: core imports no model/network; adapters
  import no authority surface.

**An LLM response is never authoritative evidence.**
