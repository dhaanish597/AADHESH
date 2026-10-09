# Deterministic obligation engine

The engine evaluates the eight construction clauses in the verified corpus. It has no model,
network, AWS, or clock dependency. The filesystem adapter verifies the corpus before supplying
an immutable snapshot; the caller supplies the evaluation time and site facts.

## Audit before implementation

Audited against the committed 29 September 2026 schedule, PDF pages 1, 2, 11, 12 and 16.
All eight original obligation IDs and primary citations are preserved. Additional quotations
provide the conditions omitted by the original single-fact representation.

| Obligation | Source conditions and correction |
|---|---|
| `grap1-cd-dust-mitigation` | Page 2 item 1 covers C&D activities and management of C&D waste in the NCR. It is not conditional on an observed dust plume. Evaluate recorded dust-mitigation and waste-management compliance; do not infer either from the presence of dusty work. Materials can still need controls when work is stopped. |
| `grap1-cd-large-project-registration` | Page 2 item 2 uses **plot size**, not built-up/project area. At or above the cited size, C&D cannot continue if the project is unregistered **and/or** fails the other Direction 11–18 remote-monitoring requirements. Size alone is not a violation. Continuing work needs both positive compliance facts; stopping work satisfies this prohibition without claiming registration. The referenced Directions are not in this corpus, so their detailed requirements cannot be computed or invented: the profile records an explicit compliance attestation, unknown by default. |
| `grap3-cd-restricted-activities` | Pages 11–12 item 1(i) enumerates activities, including specific exclusions for minor MEP welding, minor indoor repairs/maintenance, and pothole repairs. Replace the unexplained legal-classification boolean with a cited activity list. Item 1(iii) allows listed project categories only subject to waste, dust and Commission-direction compliance. A project label alone never satisfies the exception. |
| `grap3-cd-demolition` | “All demolition works.” is governed by the Stage III heading, NCR scope and the conditional category exception on page 12. A demolition fact alone is not a compliance result. Evaluate whether work is stopped or the complete conditional exception is satisfied. |
| `grap3-cd-piling` | The same context and conditional exception govern “Piling works.” Preserve the separate rule and quotation. |
| `grap3-cd-unpaved-roads` | The source concerns **vehicles carrying construction materials or C&D waste on unpaved roads**. It does not prohibit every use of an unpaved road. Use that complete activity description and the conditional project exception. |
| `grap3-cd-permitted-categories-only` | Page 12 item 1(iii) lists categories a–h and requires strict compliance. Ancillary work must be specific to and supplement a listed parent category; an unspecified “ancillary” label is insufficient. Item 1(ii) separately permits other, less-polluting activities subject to controls. Its relationship to the word “only” in 1(iii) is not unambiguously resolved by these bytes. Continuing non-listed activity at a non-listed project is therefore explicitly **UNKNOWN pending source clarification**, with both quotations, rather than a blanket ban or permission. Stopped work and the listed-activity/listed-category cases remain decidable. |
| `grap4-cd-linear-projects` | Page 16 item 3 extends the Stage III C&D ban to **linear public projects**. Evaluate the inherited listed activities and whether they have stopped. Do not extend this new ban to hospitals or every other Stage III category. Lower-stage clauses remain separately evaluated; meeting a Stage III exception does not satisfy this additional Stage IV restriction. |

Page 1 item 4 explicitly continues lower-stage actions at higher stages. Each rule carries
that citation and a citation for its own stage heading; cumulative activation is not an
uncited assumption in application code. NCR scope is an explicit site fact, not inferred from
a station, postcode, site name or location string.

The Stage IV AQI band also needed a representation correction: its original inclusive lower
bound of 451 assumed integer observations, while page 16 states `AQI > 450`. It now stores
`aqi_lower: 450, aqi_lower_inclusive: false`, preserving the original quote and handling the
strict boundary without rounding. Band verification checks stage, pollutant, bounds and
inclusivity against the quote. No threshold is a Python constant.

## Scope of a site profile

One `ConstructionSite` profile describes the activity being assessed at that site, including
whether it is continuing. For a site with several concurrent activities, evaluate a profile
for each activity; no result asserts compliance of unreported activities. `activity_type`
uses the source's activity wording, so an activity is not classified by an LLM. Missing and
JSON `null` facts remain unknown. No worker-count fact or monetary calculation is needed.

The compliance booleans are recorded site facts/attestations. They do not claim that this
corpus contains the detailed contents of every Direction or Waste Management Rule it refers
to. Unknown attestations remain unknown; the engine never generates them.

| Fact | Meaning |
|---|---|
| `site_id` | Required non-empty identifier; no legal meaning inferred from it. |
| `in_ncr` | Whether the assessed site/activity is within the cited NCR scope. |
| `plot_size_sqm` | Plot size, as used in the registration clause; not built-up area. |
| `registered_on_state_portal` | Registration on the respective State/GNCTD web portal. |
| `remote_monitoring_requirements_met` | Attested compliance with the other referenced Direction 11–18 requirements. |
| `activity_type` | Assessed activity, using the exact values in the corpus predicate lists. |
| `activity_in_progress` | Whether that activity is continuing; explicit `false` records a halt. |
| `is_minor_indoor_repair` | The stated repair/maintenance exception for coatings and flooring work. |
| `project_category` | Project category from the cited list, or the recorded non-listed category. |
| `ancillary_to_category` | The specific listed parent category supplemented by ancillary work. |
| `dust_mitigation_compliant` | Attested compliance with the cited dust prevention/control requirements. |
| `cd_waste_management_compliant` | Attested sound waste management/compliance with the cited waste rules. |
| `commission_directions_compliant` | Attested compliance with the Commission directions required for the exception. |

All facts except `site_id` default to unknown. JSON booleans must be booleans, and plot size
must be a finite, non-negative number. Unrecognised field names are rejected. The core also
accepts the existing `SiteProfile`; absent keys, JSON `null` and `UNKNOWN_FACT` all evaluate as
unknown. Both missing and explicitly unknown sentinels refuse boolean coercion.

## Rule data and outcomes

Each rule retains its primary `source_doc`, `page` and `quote`, and contains:

- `triggers_at_stage`, with `stage_evidence` and `continuation_evidence` references;
- separate `applicability` and `requirement` expression trees;
- `required_action` and its `action_evidence` references;
- named supporting `evidence`, referenced by every comparison and compound node;
- an optional cited `clarification_when` expression and explanation for unresolved wording.

The only operators are `eq`, `gte`, `in`, `not_in`, `and` and `or`. Schema validation limits
fact names to the construction vocabulary. Textual and numeric predicate literals must occur
in their referenced quotes. These checks prove the evidence and literals, not the legal
interpretation: the audit above is the reviewable interpretation. Legal conditions and
exceptions live in the JSON corpus, with no rule-ID switches in Python.

For the registration rule, applicability requires NCR scope and the cited plot size. Its
compliance tree is `activity stopped OR (registered AND other requirements satisfied)`.
Consequently size alone never establishes a violation, and a halt never claims registration.

| Result | `applicable` | Meaning |
|---|---|---|
| `MET` | `true` | Known applicability and known facts satisfying the requirement. |
| `NOT_MET` | `true` | Known applicability and a demonstrated violation. |
| `UNKNOWN` | `null` | A fact needed to establish applicability is unknown. |
| `UNKNOWN` | `true` | Compliance needs an unknown fact or the cited wording needs clarification. |
| `NOT_APPLICABLE` | `false` | No activated official stage, a lower official stage, or facts outside the clause's scope. |

Compound predicates use three-valued logic. `true OR unknown` is true because one sufficient
branch is established; `false AND unknown` is false because one necessary condition fails.
The unknown fact itself is never assigned a truth value. If an unknown fact could change the
decision, the result is `UNKNOWN`. For example, stopped piling can meet the halt requirement
without needing to know an exception category. Continuing piling at an exempt project cannot
be `MET` while a required compliance attestation is unknown.

## Official and implied stages

Current resolution selects only a verified active invocation whose effective time is not in
the future. A revoked record stays historical even if the caller supplies a January clock.
Multiple active invocations are an integrity error; an unprovable invocation is also an error.
The committed corpus contains no current invocation, so current `official_stage` is `NONE`
and every stage-triggered clause is `NOT_APPLICABLE`.

An optional observation produces only an implied stage through the verified bands. No AQI
value can activate an official stage. The output keeps both values and a `stage_status` of
`ALIGNED`, `DISCREPANCY`, `OFFICIAL_ONLY` or `NO_OFFICIAL_INVOCATION`. An undeterminable implied
stage is JSON `null`, not an invented stage below Stage I.

For implied III and official II, `DISCREPANCY` explicitly explains that Aadesh does not infer
legal activation from AQI. Applicability still uses the verified official invocation, with
that basis stated in the reason. For implied III and no invocation, the explanation says no
verified current CAQM invocation is present; Stage III clauses remain unactivated.

## Historical limitation

The January 16 invocation and January 22 revocation are verified historical records. They
refer to the November 2025 schedule, which is absent. The available obligation rules quote
the September 2026 revision. An explicit replay can apply that historical stage to the
available rules as a **scenario replay**, with this limitation on every result. It cannot
claim to reconstruct the obligations legally in force in January. Normal resolution continues
to report no verified current invocation.

`ReplayContext(invocation_date="2026-01-16", revocation_date="2026-01-22")` must match the
verified history. Optional `at` must be within `[invoked_at, revoked_at)` and include a
timezone. The result and every obligation carry `mode: REPLAY`, and every reason carries the
historical scenario limitation. The selected invocation retains lifecycle `revoked`;
`current_official_stage` remains `NONE`. The CLI never edits invocation state.

## Verification boundary

`LocalFileCorpus.snapshot()` re-verifies on each call and refuses any integrity failure.
Verification covers all primary and supporting citations; one valid primary quote cannot
hide an unproved exception. It checks the original PDF SHA-256, the hash of the cited extracted
page and the quoted text. The manifest now binds all 34 extracted pages. Before adding those
hashes, every cached page was compared with fresh extraction of the unchanged original PDFs.
Page-hash canonicalisation normalises newline conventions only.

The immutable `VerifiedCorpus` carries receipts for complete rule, band and invocation
objects, plus their citations. Changing a proved object's conditions or lifecycle cannot
reuse its old receipt. This is a trusted adapter boundary, not an unforgeable credential for
arbitrary Python callers. A reused snapshot deliberately represents its verified bytes;
obtain a fresh snapshot for each new production evaluation.

An unproved rule is listed under `excluded_obligations`, with no action emitted for it and
`fully_sourced: false`. The filesystem/CLI path refuses a damaged corpus before resolution.
Every resolved row, including inapplicable rows, carries `source_doc`, `source_page`,
`source_quote`, `source_hash` and the supporting `evidence` citations.

## Local interface

```python
from datetime import UTC, datetime
from pathlib import Path

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain import ConstructionSite
from aadesh_core.resolver import resolution_to_dict, resolve_obligations

result = resolve_obligations(
    site=ConstructionSite(site_id="site-001", in_ncr=True),
    corpus=LocalFileCorpus(Path("corpus")).snapshot(),
    now=datetime(2026, 10, 8, 9, tzinfo=UTC),
)
payload = resolution_to_dict(result)
```

`ResolutionResult` is also exported as `ObligationSet` for existing consumers. It contains
the stage assessment, all rule outcomes and exclusions, resolution time, optional observation
provenance and replay context. The core has no I/O or clock reads. CLI clock defaults are
outside the core; use `--now` for reproducible output.

```bash
make resolve ARGS="--site fixtures/sites/piling-site.json --now 2026-10-08T09:00:00+00:00"
make resolve ARGS="--site fixtures/sites/piling-site.json --replay fixtures/replays/january-2026-stage-iii.json --now 2026-10-08T09:00:00+00:00"
make resolve ARGS="--site fixtures/sites/piling-site.json --observation fixtures/observations/aqi-discrepancy.json --now 2026-10-08T09:00:00+00:00"
```

The same interface is `aadesh-resolve` after installation, or `python -m aadesh_cli.resolve`.
`--corpus` selects the local corpus directory. No bare `--stage` override is accepted: official
activation must come from verified corpus evidence. Exit codes are 0 for a fully sourced
resolution, 1 for invalid inputs and 2 for corpus-integrity failure. Errors go to stderr as
JSON; a damaged corpus produces no actions on stdout.

## Fixtures and checks

`tests/fixtures/resolution/cases.json` covers cases A–I: no invocation, official I/III/IV,
implied III versus official II, implied III without invocation, missing facts, explicit
violation and explicit satisfaction. Site examples live in `fixtures/sites/`. The observation
fixture is labelled synthetic. Stage I/II/III/IV current invocations in unit tests are explicit
test doubles, never CAQM corpus entries. Production and replay CLI tests use the real corpus.

The suite also checks compound registration, category conditions, indoor exceptions, ancillary
parent scope, narrow unpaved-road movement, Stage IV linear projects, provenance tampering,
uncited literals, stale verification and historical lifecycle changes. A subprocess runs the
real replay CLI with network connections and model imports blocked. Worker counts and monetary
input fields cannot affect the determination.

The resolver reports operational clause/status counts only. Overlapping clauses, such as the
general restricted-activity rule and the piling rule, remain separate cited rows; their count
is not a count of distinct activities, workers, monetary entitlements or avoided emissions.
No PM2.5 reduction or pollution-prevention claim is produced.

Validation: `make lint`, `make test`, `make verify`, `make check`; `make verify-tamper` must
detect the changed byte and exit non-zero. The verified corpus now has 3 official documents,
55 citation checks, 8 construction clauses, 4 stage bands and no entitlement amount.

## Changed files

The implementation changes these 58 files. Source PDFs and existing extracted page text are
unchanged; operator-supplied `corpus/incoming_sources/` files are excluded.

```text
Makefile
README.md
pyproject.toml
corpus/README.md
corpus/obligations/construction_site.json
corpus/sources/manifest.json
corpus/stage_bands/grap_stage_bands.json
docs/corpus-audit.md
docs/obligation-engine.md
fixtures/observations/aqi-discrepancy.json
fixtures/replays/january-2026-stage-iii.json
fixtures/sites/hospital-project.json
fixtures/sites/linear-project.json
fixtures/sites/piling-site.json
fixtures/sites/stopped-piling-site.json
fixtures/sites/unknown-dust-site.json
services/aadesh_adapters/corpus/local_file.py
services/aadesh_cli/corpus.py
services/aadesh_cli/resolve.py
services/aadesh_core/citations.py
services/aadesh_core/corpus_validation.py
services/aadesh_core/corpus_schemas/invoked_stage.schema.json
services/aadesh_core/corpus_schemas/obligation.schema.json
services/aadesh_core/corpus_schemas/source_manifest.schema.json
services/aadesh_core/corpus_schemas/stage_band.schema.json
services/aadesh_core/domain/__init__.py
services/aadesh_core/domain/construction.py
services/aadesh_core/domain/enums.py
services/aadesh_core/domain/facts.py
services/aadesh_core/domain/models.py
services/aadesh_core/domain/predicates.py
services/aadesh_core/explanation/deterministic.py
services/aadesh_core/ports/corpus.py
services/aadesh_core/resolver/__init__.py
services/aadesh_core/resolver/operators.py
services/aadesh_core/resolver/predicates.py
services/aadesh_core/resolver/resolver.py
services/aadesh_core/resolver/serialization.py
services/aadesh_core/stages.py
services/aadesh_core/verification/verifier.py
tests/conftest.py
tests/fixtures/resolution/cases.json
tests/fixtures/resolution/primary-citations.json
tests/support/builders.py
tests/support/corpus_builder.py
tests/support/resolution.py
tests/unit/test_construction_site.py
tests/unit/test_corpus_adversarial.py
tests/unit/test_corpus_ingest.py
tests/unit/test_corpus_loader.py
tests/unit/test_obligation_resolution.py
tests/unit/test_provenance_propagation.py
tests/unit/test_resolution_evidence.py
tests/unit/test_resolution_predicates.py
tests/unit/test_resolve_cli.py
tests/unit/test_resolver_tristate.py
tests/unit/test_resolver_unsourced.py
tests/unit/test_vertical_slice.py
```
