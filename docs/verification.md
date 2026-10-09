# Verification — what this repository proves, and what it does not

This document is the reviewer's path from "the tests are green" to "here is the property each
one establishes, and here is the property nobody has established yet".

It describes the suite in `tests/verification/`. Those tests carry no `integration` marker: they
need no Docker, no network and no AWS, so they run in the default gate (`make test`, `make check`).

```
make test            # includes tests/verification/
make check           # lint + test + verify
```

- Total: **151 tests** (151 pass — the Map state defect is fixed; see [Known gaps](#known-gaps)).
- Test corpus used by most of them: a synthetic order built under `tmp_path` by
  `tests/verification/harness.py`. **No test in this package writes to `corpus/`.**
- Where a test needs the real CAQM records it reads the shipped corpus read-only, and two tests
  assert the shipped bytes are unchanged afterwards.

| file | tests | the property it establishes |
|---|---|---|
| `test_source_integrity.py` | 14 | every citation re-proves against hashed bytes; tampering is caught and blocks loading |
| `test_legal_activation_boundary.py` | 12 | an AQI reading can never turn itself into an enforcement order |
| `test_evidence_chain.py` | 16 | one Parchi traced end to end to a hashed CAQM sentence |
| `test_cross_layer_attacks.py` | 53 | fifteen named attacks, each refused at the layer that owns the rule |
| `test_invariants.py` | 34 | properties swept over inputs, not asserted for one |
| `test_historical_replay.py` | 11 | January's real order is usable as history and inert as law |
| `test_workflow_contract.py` | 11 | the deployed state machine cannot bypass acknowledgement; the Map state declares exactly one processor (fixed) |

---

## 1. What Aadesh proves

Stated narrowly, because the narrow version is the one the tests support.

1. **A legal obligation in this system descends from bytes.** Every obligation that can be acted
   on names a document, a page and a sentence, and carries the SHA-256 of the document. A quote
   is proved by being physically present in the extracted page text, not by resembling it.

2. **An invoked stage exists only because a CAQM order says so.** The stage derived from an AQI
   reading is computed, reported, and never activates anything. This is the distinction the
   system is built around, and it is asserted from both sides: the reading really is derived, and
   it still does nothing.

3. **A Parchi records that one named worker was displaced by one invoked stage.** It can be
   traced back through the workflow execution and the standing order to the obligation and the
   CAQM source. `test_evidence_chain.py` walks that path and asserts every link is present.

4. **The worker's own confirmation is required, and happens at most once.** `PENDING_ACK →
   ACKNOWLEDGED → SEALED` is the only route; SEALED implies a prior acknowledgement; a link can
   be confirmed once and replayed freely without producing a second fact.

5. **Authorization is a gate in front of every operation, and it fails closed.** A supervisor
   cannot reach another site, a worker cannot confirm another worker's record, a facilitator
   without consent cannot view a Parchi or an assist claim.

6. **The deterministic core needs no model.** A subprocess test blocks every AI SDK and every
   network client at import time and resolves an obligation correctly with all of them
   unimportable (`test_cross_layer_attacks.py::test_13b`, `_no_model_child.py`).

7. **Tampering is detected, and detection blocks action.** `make verify` re-proves every citation;
   a tampered document makes `LocalFileCorpus.snapshot()` raise, so a tampered source produces no
   obligation at all — not a wrong one.

## 2. What Aadesh deliberately does NOT prove

The list that matters more, because each of these is a claim that could be made and would be
false.

- **Not that the CAQM corpus is legally correct or complete.** The tests prove the corpus is
  *internally consistent and faithfully transcribed*. Whether the transcribed rules are the right
  rules, and whether they are still in force, is a legal question no test answers.
- **Not that any health or environmental outcome follows.** No test asserts a PM2.5 reduction, a
  tonnage avoided, or an air-quality improvement. The corpus cites no such figure, so no test
  could honestly assert one.
- **Not that any worker is entitled to any amount.** No monetary entitlement is asserted anywhere.
  `ParchiProvenance` has no field an amount could occupy; `entitlement_refs` holds references.
  A test asserts an entitlement whose cited basis is not on the page fails verification.
- **Not that the AWS deployment works.** `test_workflow_contract.py` verifies the *machine
  contract* in `infra/stepfunctions/standing-order.asl.json` — the graph, the task-token wait, the
  no-bypass property. It does not deploy, does not run a Lambda, and does not prove that the
  handlers would satisfy the contract. See [Known gaps](#known-gaps).
- **Not that the historical replay reconstructs what was legally true in January.** The replay
  notice says this in the product, and it is repeated here: the schedule revision in force on the
  replay date is not established, so the obligations it produces are illustrative, not proof of
  historical legal obligations.
- **Not that a real worker used the system.** The acknowledgements in these tests are driven by
  test code holding the token. Nothing here proves anything about a human.
- **Not hostile-input hardening.** The attacks are the fifteen the brief names plus their
  controls. They are not a fuzzing campaign and do not stand in for one.

## 3. How source integrity is verified

The corpus is the only door, and every door has a hash on it.

- `corpus/sources/manifest.json` records, per document, its SHA-256, byte size and extracted
  page-text hashes. `test_source_integrity.py` recomputes both independently, over every document
  and every page, and asserts they match.
- Citations are re-proved by locating the quoted sentence in the named page's text after
  whitespace normalisation. `test_every_citation_in_the_shipped_corpus_re_proves` calls the
  verifier; `test_a_verified_citation_quote_is_physically_present_on_the_page_it_names`
  re-derives the same check with different code (`labelled_citations` + `normalise`) so a bug in
  the verifier cannot make the two agree.
- A paraphrase fails: `"shall be suspended"` → `"must stop"` yields `quote not found`.
- Proof, not resemblance — which is the same reason `harness.py` keeps the real schedule's en
  dashes and curly quotes rather than plain ASCII.

The failure is not merely reported; it blocks use. `LocalFileCorpus.snapshot()` raises
`CorpusIntegrityError` on a document hash mismatch, on a changed page, on a missing cited page, on
a broken quote, and on an entry with its evidence deleted. `resolve_obligations` cannot be reached.

## 4. How legal activation is separated from AQI

Two different things that are never merged:

- the **implied** stage — derived from a cited AQI band and a reading (`derive_implied_stage`);
- the **invoked** stage — which exists only because a CAQM order says so (`invoked_stage.json`).

Only the invoked stage activates a clause. `test_legal_activation_boundary.py` proves the boundary
from both sides, and the four named cases are all covered:

| case | setup | expected | test |
|---|---|---|---|
| implied → no official | shipped corpus (revoked invocation), AQI 420 implies III | no stage, nothing applicable | Case A |
| implied ≠ official | order invoked II, AQI 420 implies III | official II stays authoritative, discrepancy reported, nothing escalated | Case B |
| official only | order invoked III, reading implies nothing | Stage III clauses evaluated on facts | Case C |
| historical | real 16.01.2026 order, replayed | usable as replay only | Case D |

`test_invariants.py::test_08` turns the four cases into a property: over a sweep of readings
spanning every band boundary and three extremes, no reading on the shipped corpus produces a
current stage.

A guard test asserts the implied stage really is derived (420 → Stage III with a real citation),
so the boundary cannot be passed by never computing it.

## 5. How Parchi evidence is verified

`test_evidence_chain.py` runs the chain once — corpus → invocation → obligation → standing order →
trigger → run claim → Parchi → acknowledgement → seal — and then answers *"Why did this Parchi
exist?"* by walking the record:

```
Parchi → workflow execution → Standing Order → obligation → CAQM document/page/sentence/hash
```

Every hop is asserted present, and the last one is checked against the page file on disk rather
than against the record that describes it. `test_the_trace_is_complete_no_link_is_missing` fails
if any hop is missing, so a Parchi with a gap in its custody chain cannot pass as evidence.

Supporting properties (`test_cross_layer_attacks.py`, `test_invariants.py`):

- PENDING_ACK cannot be sealed; SEALED implies a prior acknowledgement with a method and event id.
- A link confirms once. Two to five replays produce one event, one event id, and
  `already_confirmed` on every call after the first.
- A used link is not a skeleton key: the identity check runs before the replay memo, so presenting
  someone else's used link is refused rather than honoured.
- Sealing twice returns the original freeze — a retried seal step does not rewrite `sealed_at`.
- The raw token never appears in the audit trail; only a hash-derived reference does.

## 6. How authorization is verified

`AuthorizationService` is the one place a request becomes a domain operation; the domain keeps its
own identity rule underneath it. Both locks are tested.

- **Supervisor on their own site → allowed**, on an unrelated site → `AuthorizationDenied`
  (asserted against the real Cedar policies in `infra/cedar/`).
- **A worker may confirm their own Parchi and not another's** — refused by the domain
  (`WrongWorker`) and, on the service path, by Cedar.
- **A supervisor cannot confirm a worker's Parchi**, including by re-presenting a link the worker
  has already used.
- **A facilitator cannot view a Parchi or make an assist claim without consent.** The assist
  resource is a `ClaimAssistanceContext`, not a `Parchi`, so a facilitator holding a Parchi
  reference has no resource to name the request against.
- **Unavailable authorization fails closed.** A provider raising `AuthorizationUnavailable`
  propagates out of both `require_issue_halt` and `acknowledge_own_parchi`, and the Parchi is left
  `PENDING_ACK`. There is no `except: return allowed=True` shape in the service.

Prompt 7 (Facilitator Privacy + Consent) was **not** merged into the branch this suite was built
on, and nothing here invents its implementation. The consent-related assertions above test only
the Prompt 6 contract that is actually present. When Prompt 7 lands, this section is where the
reconciliation belongs.

## 7. How replay is distinguished from current state

The one invocation on record that actually happened — CAQM's Stage III order of 16.01.2026,
revoked 22.01.2026 — is kept as evidence about the past.

- `test_historical_replay.py` uses the **real** recorded invocation and asserts it is real: the
  right document, the right dates, a proved revocation citing the revocation order. A guard fails
  if the fixture drifts to invented data.
- The replay is **usable**: it drives the real resolver, produces the historically invoked Stage
  III, and evaluates the corpus's clauses.
- The replay is **inert**: `is_current` is False, `current_stage` is None, the notice says "not a
  current invocation", and the stage it produces is refused by `evaluate_trigger` with
  `NOT_CURRENT_INVOCATION` even for an otherwise-perfect order.
- Currency is a property of the **record, not the clock**: passing a `now` from January in CURRENT
  mode still reports no stage. Only an explicit `ReplayContext` reaches the history, and then only
  in REPLAY mode.
- A replay instant outside the order's effective window is refused.
- Running a replay writes nothing — no audit record, no Parchi — and the shipped corpus is
  byte-identical afterwards (asserted).

## 8. How tamper detection works

Two mechanisms, both non-zero-on-failure, and neither "fixed" to pass.

- **`make verify`** — the positive gate. Re-proves every document hash and every citation. Exits
  `OK` only when every check passes; exits `CORPUS_NOT_READY` when the corpus is structurally
  valid but has nothing to prove, which is deliberately *not* `OK`, so an empty corpus cannot
  masquerade as a verified one. A directory with no manifest is never `OK`.
- **`make verify-tamper`** — the negative gate, a check that **must fail**. It tampers a copy and
  asserts detection. If it ever exits zero the detector is broken and the corpus claim is
  decorative. `test_verify_tamper_exits_non_zero_and_leaves_the_real_corpus_untouched` runs it on
  a copy and asserts the shipped corpus is byte-identical before and after.

What is caught: a flipped byte in a source document (hash mismatch); a changed page byte (page
hash + citation failure); a deleted cited page; a paraphrased quote; an entry with its evidence
removed; an entitlement whose cited monetary basis is not on the page it names.

What the detection *does*: it stops the load. Every one of those cases makes
`LocalFileCorpus.snapshot()` raise, so the tampered corpus cannot reach the resolver. Detection
that only reported would leave the interesting question — "and then what?" — unanswered.

---

## Known gaps

Recorded rather than hidden. Each is a claim this suite does **not** support.

1. **The Step Functions Map state defect has been corrected.** `PendingAck` in
   `infra/stepfunctions/standing-order.asl.json` previously declared **both** `Iterator` and
   `ItemProcessor`, which are mutually exclusive in ASL, and `ItemProcessor.States.BuildItem.Next`
   targeted `AwaitWorkerAck` — a state that exists only inside the sibling `Iterator.States`, not
   inside its own. This has been fixed by using a single `Iterator` mode with `BuildItem` as the
   first state constructing the worker-ack payload from `$$.Map.Item.Value` and the parent context,
   followed by `AwaitWorkerAck` using `lambda:invoke.waitForTaskToken`. The test
   `test_the_map_processor_declares_exactly_one_of_iterator_or_itemprocessor` now passes. The
   durable task-token wait, `PENDING_ACK → ACKNOWLEDGED → SEALED` flow, and no-bypass property
   are preserved.

2. **Handler behaviour is unverified.** The ASL contract says the machine *would* route
   correctly. No Lambda is implemented or executed, so nothing here proves that a deployed handler
   honours the contract it is wired into.

3. **Replay obligations are illustrative.** As section 2 says, the schedule revision in force on
   the replay date is not established.

4. **The Prompt 7 boundary.** Consent and facilitator-privacy behaviour beyond the Prompt 6
   contract is untested here by design; it must be reconciled when Prompt 7 is merged.

5. **No concurrency testing.** The idempotency guarantees are asserted by sequential replay. The
   stores' compare-and-set paths are exercised, but no test races two acknowledgements against
   each other.
