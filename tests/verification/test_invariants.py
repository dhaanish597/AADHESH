"""INVARIANTS — properties that must hold for every input, not just the one we tried.

The attack suite in `test_cross_layer_attacks.py` asks "can this specific thing be done?". This
file asks the complementary question: "is there ANY input for which the property breaks?" It
does that by sweeping a parameter space rather than picking a value, so a property that holds
only for the fixture's chosen reading is caught.

Kept to plain `pytest.mark.parametrize` on purpose. The project has no hypothesis-style
generator and adding one to prove eight properties would be a dependency carried by every
future contributor; a sweep over the real band boundaries and a few extremes costs nothing and
is legible to whoever reads it next.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.citations import labelled_citations, normalise, page_text_sha256
from aadesh_core.domain.enums import (
    ObligationStatus,
    ParchiState,
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
)
from aadesh_core.errors import IllegalParchiTransition
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    Roster,
    RosterEntry,
    WorkflowExecution,
    acknowledge_parchi,
    create_parchis_for_roster,
    seal_parchi,
)
from aadesh_core.resolver import resolve_obligations
from aadesh_core.standing_order import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    activate,
    confirm,
    fire,
)
from aadesh_core.standing_order.models import TriggerRun, deterministic_parchi_id
from aadesh_core.standing_order.trigger import StageTripEvent, evaluate_trigger
from tests.unit.test_trigger_run_store_contract import FakeTriggerRunStore
from tests.verification.harness import (
    NOW,
    ORDER_DOC,
    VALID_FROM,
    VALID_UNTIL,
    build_corpus,
    live_invocation,
    reading,
    site,
    stack,
)

WORKERS = ("wrk-1", "wrk-2", "wrk-3")

#: Readings that straddle every band boundary in the fixture, plus extremes. The boundaries are
#: where an off-by-one in the band comparison would show up.
SWEEP = (0.0, 200.0, 201.0, 300.0, 301.0, 400.0, 401.0, 420.0, 450.0, 451.0, 5000.0)


# --- every actionable obligation carries its provenance ----------------------


@pytest.mark.parametrize("value", SWEEP)
def test_01_every_obligation_that_is_acted_on_cites_a_hashed_source(
    tmp_path: Path, value: float
) -> None:
    """Whatever the reading, an obligation reported as met or unknown must name a document, a
    page and a sentence, and carry the hash of the document those came from. An obligation
    that could be acted on without provenance would be an assertion, not a finding."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))
    result = resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=NOW,
        reading=reading(value),
    )

    actionable = [
        r for r in result.results if r.status in (ObligationStatus.MET, ObligationStatus.UNKNOWN)
    ]
    assert actionable, "the sweep must reach the obligation, or the property is vacuous"
    for entry in actionable:
        assert entry.citation.source_doc == ORDER_DOC
        assert entry.citation.page > 0
        assert entry.citation.quote
        assert entry.citation.source_hash is not None
        assert len(entry.citation.source_hash) == 64


# --- every parchi has a source workflow --------------------------------------


def test_02_every_parchi_names_the_execution_that_opened_it(
    tmp_path: Path, repo_root: Path
) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts = stack(repo_root)
    execution = WorkflowExecution(
        execution_id="exec-1", site_id="site-001", source_event_id="evt-1"
    )

    issues = create_parchis_for_roster(
        execution=execution,
        roster=Roster(site_id="site-001", entries=tuple(RosterEntry(w, w) for w in WORKERS)),
        provenance=ParchiProvenance(stage=live_invocation(corpus), reading=reading(420.0)),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )

    assert len(issues) == len(WORKERS)
    for issue in issues:
        assert issue.parchi.workflow_execution_id == execution.execution_id
        assert issue.parchi.source_event_id == execution.source_event_id


# --- every acknowledgement belongs to exactly one parchi ---------------------


def test_03_every_acknowledgement_maps_to_exactly_one_parchi(
    tmp_path: Path, repo_root: Path
) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts = stack(repo_root)
    issues = create_parchis_for_roster(
        execution=WorkflowExecution(
            execution_id="exec-1", site_id="site-001", source_event_id="evt-1"
        ),
        roster=Roster(site_id="site-001", entries=tuple(RosterEntry(w, w) for w in WORKERS)),
        provenance=ParchiProvenance(stage=live_invocation(corpus), reading=reading(420.0)),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )

    confirmed = [
        acknowledge_parchi(
            payload=issue.qr.payload,
            actor_worker_id=issue.parchi.worker_id,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )
        for issue in issues
    ]

    events = parts.audit.for_event("ParchiAcknowledged")
    assert len(events) == len(WORKERS), "one event per worker, no more"
    acked_ids = [outcome.event.parchi_id for outcome in confirmed]
    assert len(set(acked_ids)) == len(acked_ids), "an acknowledgement belongs to one parchi only"
    for outcome in confirmed:
        assert outcome.parchi.worker_id == outcome.event.worker_id
        assert outcome.parchi.state is ParchiState.ACKNOWLEDGED


# --- a sealed parchi has a prior acknowledgement -----------------------------


def test_04_a_sealed_parchi_always_has_an_acknowledgement_behind_it(
    tmp_path: Path, repo_root: Path
) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts = stack(repo_root)
    (issue,) = create_parchis_for_roster(
        execution=WorkflowExecution(
            execution_id="exec-1", site_id="site-001", source_event_id="evt-1"
        ),
        roster=Roster(site_id="site-001", entries=(RosterEntry("wrk-1", "wrk-1"),)),
        provenance=ParchiProvenance(stage=live_invocation(corpus), reading=reading(420.0)),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )
    acknowledged = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id="wrk-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )
    sealed = seal_parchi(
        parchi=acknowledged.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit
    )

    assert sealed.acknowledged_at is not None
    assert sealed.acknowledged_by == "wrk-1"
    assert sealed.acknowledgement_event_id is not None
    assert sealed.acknowledgement_method is not None
    assert sealed.sealed_at is not None


def test_04b_the_only_route_to_sealed_runs_through_acknowledged(
    tmp_path: Path, repo_root: Path
) -> None:
    """The invariant above holds because the other route is closed: a PENDING_ACK parchi cannot
    be sealed, so SEALED implies a prior confirmation rather than merely accompanying one."""
    corpus = build_corpus(tmp_path / "corpus")
    parts = stack(repo_root)
    (issue,) = create_parchis_for_roster(
        execution=WorkflowExecution(
            execution_id="exec-1", site_id="site-001", source_event_id="evt-1"
        ),
        roster=Roster(site_id="site-001", entries=(RosterEntry("wrk-1", "wrk-1"),)),
        provenance=ParchiProvenance(stage=live_invocation(corpus), reading=reading(420.0)),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )
    assert issue.parchi.state is ParchiState.PENDING_ACK
    with pytest.raises(IllegalParchiTransition):
        seal_parchi(parchi=issue.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit)


# --- a parchi cannot collect two acknowledgements ----------------------------


@pytest.mark.parametrize("attempts", [2, 3, 5])
def test_05_repeated_confirmation_never_produces_a_second_event(
    tmp_path: Path, repo_root: Path, attempts: int
) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts = stack(repo_root)
    (issue,) = create_parchis_for_roster(
        execution=WorkflowExecution(
            execution_id="exec-1", site_id="site-001", source_event_id="evt-1"
        ),
        roster=Roster(site_id="site-001", entries=(RosterEntry("wrk-1", "wrk-1"),)),
        provenance=ParchiProvenance(stage=live_invocation(corpus), reading=reading(420.0)),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )

    outcomes = [
        acknowledge_parchi(
            payload=issue.qr.payload,
            actor_worker_id="wrk-1",
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )
        for _ in range(attempts)
    ]

    assert len(parts.audit.for_event("ParchiAcknowledged")) == 1
    assert [o.already_confirmed for o in outcomes] == [False] + [True] * (attempts - 1)
    assert len({o.event.event_id for o in outcomes}) == 1


# --- a fingerprint executes once ---------------------------------------------


def test_06_a_trigger_fingerprint_can_start_exactly_one_run(tmp_path: Path) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    invocation = live_invocation(corpus)
    order = _fired_order()
    fingerprint = order.compute_trigger_fingerprint(
        order_doc_id=invocation.order_doc_id, order_sha256=invocation.order_sha256
    )
    store = FakeTriggerRunStore()
    run = TriggerRun(
        fingerprint=fingerprint,
        standing_order_id=order.standing_order_id,
        site_id=order.site_id,
        stage=3,
        order_doc_id=invocation.order_doc_id,
        order_sha256=invocation.order_sha256,
        started_at=NOW,
        status=StandingOrderStatus.TRIGGERED,
        parchi_ids=(deterministic_parchi_id(fingerprint=fingerprint, worker_id="wrk-1"),),
    )

    claimed = {id(store.claim(run)) for _ in range(4)}

    assert len(claimed) == 1, "four redeliveries must yield one run, not four"


def test_06b_a_spent_order_refuses_a_second_trigger(tmp_path: Path) -> None:
    """The other half: even if the run store were bypassed entirely, the order itself will not
    fire twice. A pre-commitment is spent on its first matched trigger."""
    corpus = build_corpus(tmp_path / "corpus")
    invocation = live_invocation(corpus)
    order = _fired_order()

    decision = evaluate_trigger(
        order=order, event=StageTripEvent(invoked=invocation, site_id=order.site_id), now=NOW
    )

    assert decision.fires is False
    assert decision.refusal.code == "ALREADY_TRIGGERED"


def test_06c_two_different_orders_get_two_different_fingerprints(tmp_path: Path) -> None:
    """The control for (6): the key is per order, so it cannot be collapsing every trigger into
    one and passing the uniqueness check for the wrong reason."""
    corpus = build_corpus(tmp_path / "corpus")
    invocation = live_invocation(corpus)
    first, second = _fired_order(standing_order_id="so-1"), _fired_order(standing_order_id="so-2")

    assert first.compute_trigger_fingerprint(
        order_doc_id=invocation.order_doc_id, order_sha256=invocation.order_sha256
    ) != second.compute_trigger_fingerprint(
        order_doc_id=invocation.order_doc_id, order_sha256=invocation.order_sha256
    )


# --- a verified citation requires matching bytes -----------------------------


def test_07_every_citation_in_a_proved_corpus_sits_on_the_page_it_names(
    tmp_path: Path,
) -> None:
    """Swept over every citation in the corpus rather than one: each quote is physically present
    on its named page, and that page's bytes hash to what the manifest recorded."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(2, 3))
    manifest_payload = json.loads(
        (corpus / "sources" / "manifest.json").read_text(encoding="utf-8")
    )
    manifest = {doc["doc_id"]: doc for doc in manifest_payload["documents"]}

    seen = 0
    for path in sorted(corpus.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        for _, citation in labelled_citations(json.loads(path.read_text(encoding="utf-8"))):
            document = manifest[citation["source_doc"]]
            text = (corpus / document["pages_dir"] / f"p{citation['page']}.txt").read_text(
                encoding="utf-8"
            )
            assert normalise(citation["quote"]) in normalise(text), (
                f"{path.name} p{citation['page']}"
            )
            assert page_text_sha256(text) == document["page_sha256"][str(citation["page"])]
            seen += 1

    assert seen >= 5, f"expected the fixture's citations to be swept, only saw {seen}"


def test_07b_the_document_hash_is_over_the_bytes_not_the_path(tmp_path: Path) -> None:
    """The hash must be content, not identity. Same path, one byte different, different hash."""
    corpus = build_corpus(tmp_path / "corpus")
    document = next((corpus / "sources").glob("*.pdf"))
    original = hashlib.sha256(document.read_bytes()).hexdigest()

    body = bytearray(document.read_bytes())
    body[0] ^= 0x01
    document.write_bytes(bytes(body))

    assert hashlib.sha256(document.read_bytes()).hexdigest() != original


# --- a current invocation cannot be derived from AQI alone -------------------


@pytest.mark.parametrize("value", SWEEP)
def test_08_no_reading_produces_a_current_invocation_by_itself(
    shipped_corpus: Path, value: float
) -> None:
    """The shipped corpus carries a revoked invocation and no live one. Sweep every reading --
    including ones deep inside Stage III and Stage IV -- and there is still no current stage.

    This is the property, as opposed to the four named cases: it must hold for every value, not
    for the four the brief happened to list.
    """
    result = resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(shipped_corpus).snapshot(),
        now=NOW,
        reading=reading(value),
    )

    assert result.stage is None
    assert result.current_stage is None
    assert result.applicable == ()


# --- helpers ------------------------------------------------------------------


def _fired_order(*, standing_order_id: str = "so-1") -> StandingOrder:
    order = StandingOrder(
        standing_order_id=standing_order_id,
        site_id="site-001",
        supervisor_id="sup-1",
        trigger=StageInvocationTrigger(stage=3, match=StageMatch.EXACT),
        actions=(StandingOrderActionClause(action=StandingOrderAction.ISSUE_HALT),),
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        status=StandingOrderStatus.DRAFT,
        created_at=VALID_FROM,
    )
    order = confirm(order, supervisor_id="sup-1", now=VALID_FROM)
    return fire(activate(order, now=VALID_FROM), now=NOW)
