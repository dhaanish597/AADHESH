# Corpus audit — authoritative CAQM GRAP sources

This report is the reviewer's path from a rule the system enforces back to the official bytes
it came from:

> rule → page → exact quote → extracted text → source PDF → SHA-256 → official CAQM URL

Every legal fact in `corpus/` was copied VERBATIM from the extracted text of an official CAQM
document. No threshold, action or amount was taken from memory, a news article, the hackathon
strategy documents, or this report. If a quote is not an exact substring of the page it cites,
`make verify` fails and the entry is excluded from resolution.

- Date of audit: 2026-10-08
- Ingestion tool: `make corpus ARGS="ingest …"` (`aadesh_cli.corpus`) — the only sanctioned door
- Verification tool: `make verify` (`aadesh_cli.verify`)

---

## 1. Documents ingested

All three files were placed in `corpus/incoming_sources/` by the operator. Before encoding
anything, each was re-downloaded from `caqm.nic.in` and the bytes were compared by SHA-256: all
three are **byte-identical** to the official downloads, so the committed PDFs *are* the
authoritative documents.

| doc_id | title | publisher | pages | bytes | SHA-256 | retrieved (UTC) |
|---|---|---|---|---|---|---|
| `caqm-grap-schedule-2026-09-29` | Revised GRAP for NCR — Revision 29.09.2026 | Commission for Air Quality Management in NCR and Adjoining Areas | 17 | 767 528 | `473e245b758c68be776b1d732be288abdbb5bd9084abf8fcdde9bcd3afcfa413` | 2026-10-08T09:37:31Z |
| `caqm-grap-stage3-order-2026-01-16` | Order dated 16.01.2026 — Invocation of actions under Stage III | Commission for Air Quality Management in NCR and Adjoining Areas | 9 | 8 523 939 | `358134752e712d7aa807bda8d5e4987d8c39ae747dc3c08db93c59d4ff8d0839` | 2026-10-08T09:37:46Z |
| `caqm-grap-stage3-revocation-2026-01-22` | Order dated 22.01.2026 — Revocation of actions under Stage III | Commission for Air Quality Management in NCR and Adjoining Areas | 8 | 8 355 756 | `e9317ed508bfb511f6694e330bacde8ceff6dcfe5d6703f9b96e53c6aef98996` | 2026-10-08T09:37:47Z |

### Official URLs recorded in `corpus/sources/manifest.json`

```
caqm-grap-schedule-2026-09-29
  https://caqm.nic.in/FileUploadDomain/WebsiteDocument/GRAP/GRAP%20Schedule/01fcdebf-83e1-4cfe-bc0c-d0b1470a4d4e.pdf

caqm-grap-stage3-order-2026-01-16
  https://caqm.nic.in/FileUploadDomain/WebsiteDocument/Home/News/GRAP%20Order%20dated%20160120267385c1a4-d360-44ad-9eae-54fa5c0e8f65.pdf

caqm-grap-stage3-revocation-2026-01-22
  https://caqm.nic.in/FileUploadDomain/WebsiteDocument/Home/News/GRAP%20Order%20dated%20220120265838a44f-e5d0-4f6a-8f73-390ef0d3966d.pdf
```

The filename UUIDs on `caqm.nic.in` match the operator-provided filenames exactly, which is
independent corroboration that these are the official objects. No mirror URL is recorded
anywhere; ingestion (`aadesh_core.sources.is_official_source_url`) and verification both refuse
a document whose `source_url` is not on `caqm.nic.in`.

### ⚠ Discrepancy to flag: the schedule revision date

The task brief describes source **A** as the "Revised Graded Response Action Plan, Date:
**21.11.2025**". The document actually provided, and the current official schedule at the URL
above, is stamped **(Revision: 29.09.2026)** — a later revision.

- Both January orders themselves refer to "the modified schedule of GRAP vide order dated
  **21.11.2025**". That is the revision those orders were operating under.
- We did **not** possess, and did not ingest, the 21.11.2025 schedule. We encoded the current
  schedule we hold (29.09.2026) and cite it exactly as printed.
- The AQI bands are identical between the two revisions (the classification clause is
  unchanged), so the stage-band citations are unaffected. Some Stage I C&D wording differs
  between revisions; we cite the 29.09.2026 wording because that is the document we hold.

**Nothing was encoded from the 21.11.2025 revision**, because we hold no official bytes for it.

---

## 2. Verified citations

`make verify` output at the time of this audit:

```
source documents
  manifest entries        : 3
  bytes verified (sha-256): 3
citations
  entries checked         : 14
  verified verbatim       : 14
  failed                  : 0
VERIFIED - 3 source object(s) and 14 citation(s) re-proved against indexed source bytes.
```

**14 verified citations**: 4 stage bands + 8 construction obligations + 1 historical invocation
+ 1 revocation.

---

## 3. Stage bands (from the authoritative schedule)

`corpus/stage_bands/grap_stage_bands.json`. These are legal thresholds and exist nowhere else —
a guard test fails the build if an AQI-range literal appears in `aadesh_core/domain` or
`aadesh_core/resolver`.

| stage | pollutant | range | doc | page | verbatim quote |
|---|---|---|---|---|---|
| I | AQI | 201–300 | `…schedule-2026-09-29` | 2 | `Stage I – ‘Poor’ Air Quality (DELHI AQI ranging between 201-300)` |
| II | AQI | 301–400 | `…schedule-2026-09-29` | 9 | `Stage II – ‘Very Poor’ Air Quality (DELHI AQI ranging between 301-400)` |
| III | AQI | 401–450 | `…schedule-2026-09-29` | 11 | `Stage III – ‘Severe’ Air Quality (DELHI AQI ranging between 401-450)` |
| IV | AQI | > 450 | `…schedule-2026-09-29` | 16 | `Stage IV – ‘Severe +’ Air Quality (DELHI AQI > 450)` |

**Transformation note (open, documented):** Stage IV is printed as `AQI > 450` (strict). Because
`aqi_lower` is an inclusive bound and Stage III already owns 401–450, Stage IV was encoded with
`aqi_lower = 451`, `aqi_upper = null`. This is the only place a numeric value was derived rather
than copied, and it is exactly `>450` restated for integer AQI. No band below 201 exists, so a
reading under 201 is honestly *undeterminable*, not Stage I.

---

## 4. Construction-site obligations

Scope is deliberately ONE entity type, `construction_site`. Vehicle, school, industrial,
traffic, stubble-burning, waste-sector and general citizen-charter measures were **not encoded**
(see §6). Each obligation keys on a single site-profile fact; a missing or unknown fact resolves
to `UNKNOWN`, never to “does not apply”.

| obligation_id | stage | site fact (operator value) | doc p. | verbatim quote |
|---|---|---|---|---|
| `grap1-cd-dust-mitigation` | I | `has_dust_generating_activity` eq `true` | 2 | `Ensure proper implementation of Directions/ Rules/ Guidelines for enforcement of dust mitigation measures` |
| `grap1-cd-large-project-registration` | I | `plot_size_sqm` gte `500` | 2 | `do not permit C&D activities in respect of such C&D projects with plot size equal to or more than 500 sqm , which are not registered on the ‘web portal’ of the respective State / GNCTD` |
| `grap3-cd-restricted-activities` | III | `performs_restricted_cd_activity` eq `true` | 11 | `Enforce strict restrictions on the following categories of dust generating/ air pollution causing construction and demolition ( C&D) activities in the entire NCR` |
| `grap3-cd-demolition` | III | `performs_demolition` eq `true` | 11 | `All demolition works.` |
| `grap3-cd-piling` | III | `performs_piling` eq `true` | 11 | `Piling works.` |
| `grap3-cd-unpaved-roads` | III | `moves_material_on_unpaved_road` eq `true` | 12 | `Movement of vehicles carrying construction materials or C&D waste on unpaved roads.` |
| `grap3-cd-permitted-categories-only` | III | `is_permitted_cd_project_category` eq `false` | 12 | `All C&D related activities , including those under 1(i) above , shall be continued to be permitted only for the following categories of projects` |
| `grap4-cd-linear-projects` | IV | `is_linear_public_project` eq `true` | 16 | `Ban C&D activities, as in the GRAP Stage- III, also for linear public projects such as highways, roads, flyo vers, overbridges, power transmission, pipelines, tele - communication etc.` |

Obligations at stages III/IV set `consequence.issues_parchi = true` (work halts → a worker may
be displaced); the Stage I measures do not.

**Encoding judgement (open, documented):** the obligation model compares ONE site fact per
obligation, so a clause with two conditions cannot be reproduced exactly. For
`grap1-cd-large-project-registration` the source conditions on *both* `plot size ≥ 500 sqm` and
*not registered*; we keyed on `plot_size_sqm ≥ 500` and left the registration condition in the
label and quote rather than inventing a compound fact. This is a known modelling limit, recorded
here rather than papered over.

---

## 5. Invoked stage: historical vs current

`corpus/invoked_stage.json` records ONE invocation, and it is **revoked**:

| field | value |
|---|---|
| stage | 3 |
| lifecycle | `revoked` |
| invoked_at | 2026-01-16T00:00:00+05:30 |
| order | `caqm-grap-stage3-order-2026-01-16` (p.1, sha256 `35813475…`) |
| invocation quote | `the Sub Committee on GRAP hereby decide to invoke all actions under Stage-III ('Severe' Air Quality of Delhi, ranging 4O1-45Of of extant schedule of GRAP, with immediate effect in right earnest by all the agencies concerned in Delhi-NCR,` |
| revoked_at | 2026-01-22T00:00:00+05:30 |
| revocation order | `caqm-grap-stage3-revocation-2026-01-22` (p.1, sha256 `e9317ed5…`) |
| revocation quote | `The Sub-Committee, accordingly, decides to revoke its orders dated 16.01.2026, for invoking actions under Stage-III ('Severe' Air Quality) of Schedule of GRAP (modified on 21.11.2025), with immediate effect.` |

**How the model keeps current state apart from replay state.** `InvokedStage` gained a
`lifecycle` (`active` / `revoked`), a `revoked_at`, and a `revocation_citation`. The loader’s
`invoked_stage()` returns **only an active invocation**, so the revoked January record can never
be applied:

```
LocalFileCorpus("corpus").invoked_stage()          -> None            # nothing in force now
LocalFileCorpus("corpus").invocation_history()     -> (Stage 3, REVOKED,)
  .describe() -> "Historical replay: CAQM invoked Stage 3 on 2026-01-16, revoked 2026-01-22.
                  This stage is not currently in force."
```

So the system can say **“Historical replay: CAQM invoked Stage III on 16 Jan 2026”** while
current resolution correctly determines nothing applicable — it does **not** conclude “Stage III
is currently active”.

Two further guards make the distinction tamper-evident:

- The revocation is itself a citation. If its quote were removed, `make verify` fails and the
  loader refuses the whole record (an assertion cannot enter the corpus).
- **The invocation quote must name the stage it invokes.** Editing `stage` from 3 to 4 while
  leaving the sentence untouched now fails verification, because the sentence no longer supports
  the claim. This directly addresses failure mode #5 in §7.

### OCR artefacts in the invocation quote — read this before judging the quote

The two January orders are scans whose embedded text layer is OCR-noisy. The extracted text of
order `16012026` p.1 renders some glyphs wrongly — visibly, `0`→`O` and `)`→`f`. The invocation
quote is copied VERBATIM from that extracted text, so it contains those artefacts
(`4O1-45Of`, `shouln`, `seuere`, etc.). A reviewer opening the PDF sees `401-450`; the text
layer says `4O1-45O`. We cite the text layer, because that is what `make verify` can re-prove
against the bytes.

The clean, artefact-free part of the sentence (`…hereby decide to invoke all actions under
Stage-III…`) is what carries the stage; the artefacts sit inside the parenthetical range. This
is a limitation of the source document, not of the encoding, and it is why the quote is quoted
rather than summarised.

---

## 6. Rules deliberately NOT encoded, and why

Encoding more was rejected at every point where provenance was uncertain:

- **21.11.2025 schedule.** Referenced by the January orders, but we hold no official bytes for
  it. Dropped.
- **Direction No. 97 dated 20.02.2026** ("Mitigation of dust in construction and demolition
  projects — Management of demolition waste"). **Not ingested**: no obligation in this
  construction-site workflow requires it. Adding it would only inflate the rule count.
- **Vehicle / traffic measures** (Stage III items 4–7, Stage IV items 1–2), **stone crushers /
  mining** (Stage III 2–3), **schools** (Stage III 8), **offices / WFH** (Stage III 9–10),
  **industry, DG sets, firecrackers, thermal plants** and the **CITIZEN CHARTER** — all out of
  scope: one entity type, one workflow.
- **Stage II item 4** ("Intensify inspections … at C&D sites") — an enforcement instruction to
  agencies, not a condition on a construction site.
- **Entitlement amounts.** `corpus/entitlements/cess_fund.json` is left **empty**. No
  authoritative CAQM document we hold states a rupee figure, and the task forbids inventing one.
  Aadesh reports provable worker-event metrics (worker-days, acknowledgement count, parchi
  count) instead.
- **The 21.11.2025 C&D wording, "remove C&D waste immediately" citizen-charter line, and any
  measure not tied to a site fact** — omitted rather than interpreted.

---

## 7. Adversarial provenance tests (scratch copies)

`tests/unit/test_corpus_adversarial.py` copies the committed corpus to a temp directory, makes
exactly one hostile edit, and asserts refusal. The real corpus is never touched. Run with
`make test`.

| # | hostile edit | expected | test |
|---|---|---|---|
| 1 | flip one source PDF byte | verification FAILS (hash mismatch) | `test_a_changed_source_byte_fails_verification` |
| 2 | change a quoted sentence | verification FAILS (quote not found) | `test_a_changed_quoted_sentence_fails_verification` |
| 3 | change a cited page number | verification FAILS | `test_a_changed_cited_page_fails_verification` |
| 4 | change a manifest URL to a mirror | ingestion AND verification FAIL | `test_a_non_official_mirror_url…`, `test_a_mirror_url_in_the_manifest_fails_verification` |
| 5 | change `invoked_stage` without its quote | verification FAILS (quote does not name the stage) | `test_changing_the_invoked_stage_without_its_quote_fails_verification` |
| 6 | delete the source PDF, keep page text | verification FAILS (file missing) | `test_a_deleted_source_pdf_fails_verification_even_with_page_text` |
| 7 | replace a quote with a paraphrase | verification FAILS | `test_a_paraphrased_quote_fails_verification` |

Additionally, `tests/unit/test_invocation_lifecycle.py` pins the current-vs-replay distinction:
an active invocation loads as current, a revoked one is history and is **never** returned by
`invoked_stage()`, and a revocation with no citation is refused.

No test was weakened to pass. The two tests that previously asserted the corpus was *empty*
(`test_the_shipped_repo_corpus_is_in_the_not_ready_state`,
`test_the_shipped_corpus_loads_empty`) were **strengthened**: they now assert the corpus is
populated and every citation in it re-proves. `make verify-tamper` still exits non-zero and
detects the flipped byte (12 dependent citations fail).

---

## 8. Commands and results

| command | result |
|---|---|
| `make lint` | pass — `All checks passed!`, 72 files formatted |
| `make test` | **236 passed** |
| `make verify` | **VERIFIED** — 3 documents, 14 citations, 0 failed (exit 0) |
| `make check` | pass (lint + tests + citation gate, exit 0) |
| `make verify-tamper` | exit non-zero, detection confirmed (expected — the failure IS the proof) |

---

## 9. Trace example (one rule, end to end)

`grap3-cd-demolition`

1. **Rule** — `corpus/obligations/construction_site.json`, `obligation_id: grap3-cd-demolition`.
2. **Page** — `4` of `caqm-grap-schedule-2026-09-29` (Stage III item 1(i), p.11 of the PDF).
3. **Quote** — `All demolition works.`
4. **Extracted text** — `corpus/sources/pages/caqm-grap-schedule-2026-09-29/p11.txt`.
5. **Source PDF** — `corpus/sources/caqm-grap-schedule-2026-09-29.pdf`.
6. **SHA-256** — `473e245b758c68be776b1d732be288abdbb5bd9084abf8fcdde9bcd3afcfa413`.
7. **Official URL** — `https://caqm.nic.in/FileUploadDomain/WebsiteDocument/GRAP/GRAP%20Schedule/01fcdebf-83e1-4cfe-bc0c-d0b1470a4d4e.pdf`

`make verify` re-hashes the PDF, re-reads `p11.txt`, and finds the quote verbatim.

---

## 10. Known limitations (stated, not hidden)

1. **OCR artefacts** in the two January order PDFs (§5). The invocation quote carries them
   verbatim; the schedule PDF extracts cleanly.
2. **Schedule revision mismatch** with the brief (§1): encoded 29.09.2026, not 21.11.2025.
3. **Stage IV bound derived** from `> 450` to `aqi_lower = 451` (§3).
4. **One fact per obligation** — the `plot_size_sqm` / registration clause is a single-condition
   approximation (§4).
5. **No entitlement amount** is encoded; none is claimable from these documents.
6. **No currently-invoked stage is recorded.** As of this audit the corpus proves the January
   Stage III invocation was revoked; it does **not** assert what (if anything) is in force in
   October 2026, because no order establishing that has been ingested.
