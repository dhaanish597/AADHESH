"""EVIDENCE CHAIN — one Parchi, traced all the way back to a hashed CAQM sentence.

This is the test the whole layer exists for. It runs the chain once, end to end, and then
answers the only question an auditor actually asks:

    Why did this Parchi exist?

The answer must be a walkable path -- Parchi -> workflow execution -> Standing Order -> the
obligation that was resolved -> the CAQM document, page, sentence and hash that obligation
cites -- and it must contain no link that was supplied by a model, or by the test.

The corpus here is a synthetic test order built under tmp_path (it is NOT CAQM data and the
fixture says so); the Cedar policy set, the resolver, the parchi service and the verifier are
the real production ones. The historical replay of the real January order is in
test_historical_replay.py.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.authorization import AuthorizationService
from aadesh_core.domain import Principal
from aadesh_core.domain.enums import (
    ParchiState,
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
)
from aadesh_core.errors import AuthorizationDenied
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack import (
    Roster,
    RosterEntry,
    WorkflowExecution,
    acknowledge_parchi,
    create_parchis_for_roster,
    parse_acknowledgement_payload,
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
    OBLIGATION_ID,
    ORDER_DOC,
    VALID_FROM,
    VALID_UNTIL,
    build_corpus,
    reading,
    site,
    stack,
)

SUPERVISOR = "sup-1"
WORKER = "wrk-1"
SITE_ID = "site-001"
EXECUTION_ID = "exec-2026-10-08-1"
SOURCE_EVENT_ID = "evt-stage-trip-1"


@dataclass
class Chain:
    """Everything the chain produced, so each test can assert on the part it cares about."""

    parchi: Parchi
    sealed: Parchi
    order: StandingOrder
    run: TriggerRun
    trace: dict
    audit: object
    raw_token: str
    corpus: Path


@pytest.fixture
def chain(tmp_path: Path, repo_root: Path) -> Chain:
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))
    loader = LocalFileCorpus(corpus)
    snapshot = loader.snapshot()
    invocation = loader.invoked_stage()
    assert invocation is not None

    parts = stack(repo_root)

    # 1. Resolve: the official Stage III invocation activates the cited clause.
    resolution = resolve_obligations(site=site(), corpus=snapshot, now=NOW, reading=reading(420.0))
    assert [r.obligation_id for r in resolution.applicable] == [OBLIGATION_ID]
    obligation_result = resolution.applicable[0]

    # 2. Authorize the supervisor against the real Cedar policies before anything is committed.
    authz = AuthorizationService(authz=parts.cedar)
    authz.require_issue_halt(
        principal=Principal(SUPERVISOR, "supervisor", SITE_ID), site_id=SITE_ID, now=NOW
    )

    # 3. The Standing Order: drafted, signed, activated, then fired exactly once.
    order = StandingOrder(
        standing_order_id="so-1",
        site_id=SITE_ID,
        supervisor_id=SUPERVISOR,
        trigger=StageInvocationTrigger(stage=3, match=StageMatch.EXACT),
        actions=(
            StandingOrderActionClause(action=StandingOrderAction.ISSUE_HALT),
            StandingOrderActionClause(action=StandingOrderAction.OPEN_PARCHI_PER_WORKER),
        ),
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        status=StandingOrderStatus.DRAFT,
        created_at=VALID_FROM,
    )
    order = confirm(order, supervisor_id=SUPERVISOR, now=VALID_FROM)
    order = activate(order, now=VALID_FROM)

    decision = evaluate_trigger(
        order=order, event=StageTripEvent(invoked=invocation, site_id=SITE_ID), now=NOW
    )
    assert decision.fires is True
    assert decision.fingerprint == order.compute_trigger_fingerprint(
        order_doc_id=invocation.order_doc_id, order_sha256=invocation.order_sha256
    ), "the decision must be keyed on the order, not on the event alone"
    order = fire(replace(order, trigger_fingerprint=decision.fingerprint), now=NOW)

    # 4. Claim the run: create-if-absent keyed on the trigger fingerprint.
    run_store = FakeTriggerRunStore()
    run = run_store.claim(
        TriggerRun(
            fingerprint=decision.fingerprint,
            standing_order_id=order.standing_order_id,
            site_id=order.site_id,
            stage=invocation.stage,
            order_doc_id=invocation.order_doc_id,
            order_sha256=invocation.order_sha256,
            started_at=NOW,
            status=StandingOrderStatus.TRIGGERED,
            parchi_ids=(
                deterministic_parchi_id(fingerprint=decision.fingerprint, worker_id=WORKER),
            ),
        )
    )

    # 5. Create the Parchi, carrying the resolution's provenance into the record.
    execution = WorkflowExecution(
        execution_id=EXECUTION_ID, site_id=SITE_ID, source_event_id=SOURCE_EVENT_ID
    )
    roster = Roster(site_id=SITE_ID, entries=(RosterEntry(WORKER, "Worker One"),))
    from aadesh_core.parchi_ack import ParchiProvenance

    issues = create_parchis_for_roster(
        execution=execution,
        roster=roster,
        provenance=ParchiProvenance(
            stage=invocation,
            reading=reading(420.0),
            obligation_ids=(obligation_result.obligation_id,),
            entitlement_refs=(),
            readiness_checklist=(),
            displaced_worker_days=1,
        ),
        idempotency_key=run.fingerprint,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )
    assert len(issues) == 1 and issues[0].qr is not None
    issued, qr = issues[0].parchi, issues[0].qr
    assert issued.state is ParchiState.PENDING_ACK

    # 6. The worker confirms with their own link. Nobody else can.
    outcome = acknowledge_parchi(
        payload=qr.payload,
        actor_worker_id=WORKER,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )
    assert outcome.parchi.state is ParchiState.ACKNOWLEDGED

    # 7. Seal. Sealing is a separate act from confirming, and it is what freezes the record.
    sealed = seal_parchi(
        parchi=outcome.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit
    )
    assert sealed.state is ParchiState.SEALED

    return Chain(
        parchi=issued,
        sealed=sealed,
        order=order,
        run=run,
        trace=_trace(sealed, obligation_result, resolution),
        audit=parts.audit,
        raw_token=parse_acknowledgement_payload(qr.payload),
        corpus=corpus,
    )


def _trace(parchi: Parchi, obligation_result, resolution) -> dict:
    """The chain of custody, read off the sealed record rather than reconstructed."""
    citation = obligation_result.citation
    return {
        "parchi_id": parchi.parchi_id,
        "workflow_execution_id": parchi.workflow_execution_id,
        "source_event_id": parchi.source_event_id,
        "order_doc_id": parchi.stage.order_doc_id if parchi.stage else None,
        "order_sha256": parchi.order_sha256,
        "obligation_id": obligation_result.obligation_id,
        "source_doc": citation.source_doc,
        "source_page": citation.page,
        "source_quote": citation.quote,
        "source_hash": citation.source_hash,
        "official_stage": resolution.stage.stage if resolution.stage else None,
    }


# --- the chain completes -----------------------------------------------------


def test_the_chain_reaches_a_sealed_parchi(chain: Chain) -> None:
    assert chain.sealed.state is ParchiState.SEALED
    assert chain.sealed.content_hash is not None


def test_the_sealed_record_still_names_the_order_it_was_issued_under(chain: Chain) -> None:
    assert chain.sealed.order_sha256 == chain.trace["order_sha256"]
    assert chain.trace["order_doc_id"] == ORDER_DOC


# --- "why did this Parchi exist?" --------------------------------------------


def test_a_parchi_can_be_traced_to_the_workflow_execution_that_created_it(chain: Chain) -> None:
    assert chain.trace["workflow_execution_id"] == EXECUTION_ID
    assert chain.trace["source_event_id"] == SOURCE_EVENT_ID


def test_that_execution_can_be_traced_to_the_standing_order_that_authorised_it(
    chain: Chain,
) -> None:
    run = chain.run
    assert run.standing_order_id == chain.order.standing_order_id
    assert run.site_id == chain.order.site_id
    assert run.stage == chain.order.trigger.stage
    assert run.fingerprint == chain.order.trigger_fingerprint


def test_the_run_fingerprint_is_re_derived_from_the_order_and_the_invocation(
    chain: Chain,
) -> None:
    """Not just copied: recompute it from the order and the invocation document the run names.
    A fingerprint that only agreed by assignment would not bind the run to either."""
    run = chain.run
    assert run.fingerprint == chain.order.compute_trigger_fingerprint(
        order_doc_id=run.order_doc_id, order_sha256=run.order_sha256
    )


def test_the_fingerprint_is_bound_to_the_order_document_not_just_the_stage(
    chain: Chain,
) -> None:
    """Firing on a different CAQM order -- same site, same stage -- is a different pre-commitment,
    so the run cannot be re-pointed at a swapped document."""
    assert chain.order.compute_trigger_fingerprint(
        order_doc_id="some-other-order", order_sha256=chain.trace["order_sha256"]
    ) != chain.order.compute_trigger_fingerprint(
        order_doc_id=ORDER_DOC, order_sha256=chain.trace["order_sha256"]
    )


def test_that_standing_order_can_be_traced_to_a_signed_commitment(chain: Chain) -> None:
    assert chain.order.signed_at is not None
    assert chain.order.commitment_hash == chain.order.compute_commitment_hash()


def test_the_obligation_can_be_traced_to_the_caqm_document_page_and_sentence(
    chain: Chain,
) -> None:
    """The last link, checked against the bytes rather than against the record that describes
    them: go to the page file the citation names and find the sentence on it."""
    trace = chain.trace
    assert trace["source_doc"] == ORDER_DOC
    assert trace["source_page"] == 4

    page = (
        chain.corpus / "sources" / "pages" / ORDER_DOC / f"p{trace['source_page']}.txt"
    ).read_text(encoding="utf-8")
    assert trace["source_quote"] in page

    assert trace["source_hash"] == chain.parchi.order_sha256


def test_the_trace_is_complete_no_link_is_missing(chain: Chain) -> None:
    """Every hop must be present. A Parchi with a gap in its custody chain is not evidence."""
    assert all(value is not None for value in chain.trace.values()), chain.trace


# --- what the record does NOT claim ------------------------------------------


def test_the_parchi_claims_no_monetary_entitlement(chain: Chain) -> None:
    """No compensation figure is invented anywhere in the record, because none is cited."""
    assert chain.parchi.entitlement_refs == ()
    assert chain.sealed.entitlement_refs == ()


def test_the_parchi_cites_a_measurement_and_says_so(chain: Chain) -> None:
    """The reading that triggered this is a measured observation, and the record states that
    rather than leaving it ambiguous."""
    assert chain.parchi.cites_measured_data is True


def test_nothing_in_the_trace_is_generated_text(chain: Chain) -> None:
    """Every identifier in the trace is an id from the corpus, a hex hash, or an id the domain
    minted. The prose in it -- the citation quote -- is copied from the page, not written."""
    for key in ("order_sha256", "source_hash"):
        value = chain.trace[key]
        assert value is not None and all(c in "0123456789abcdef" for c in value), key
    assert " " not in chain.trace["source_hash"]

    page_file = (
        chain.corpus / "sources" / "pages" / ORDER_DOC / f"p{chain.trace['source_page']}.txt"
    )
    assert chain.trace["source_quote"] in page_file.read_text(encoding="utf-8")


# --- the audit trail ---------------------------------------------------------


def test_the_audit_trail_records_both_transitions(chain: Chain) -> None:
    events = [record.event for record in chain.audit.records]
    assert "ParchiAcknowledged" in events
    assert "ParchiSealed" in events


def test_the_audit_trail_never_contains_the_raw_token(chain: Chain) -> None:
    assert chain.raw_token not in chain.audit.all_text()
    assert chain.raw_token not in chain.sealed.acknowledgement_token_ref


def test_the_audit_trail_correlates_the_replay_without_the_token(chain: Chain) -> None:
    """The token reference is what lets an operator tie an acknowledgement to its replay later,
    and it is derived from the hash, so it discloses nothing."""
    assert chain.sealed.acknowledgement_token_ref is not None
    assert chain.sealed.acknowledgement_token_ref in chain.audit.all_text()


# --- authorization actually gated this ---------------------------------------


def test_an_unrelated_supervisor_could_not_have_started_this_chain(
    repo_root: Path,
) -> None:
    """The supervisor who signed is assigned to this site. A supervisor assigned elsewhere is
    refused by Cedar before any order can be fired."""
    authz = AuthorizationService(authz=stack(repo_root).cedar)
    with pytest.raises(AuthorizationDenied):
        authz.require_issue_halt(
            principal=Principal("sup-2", "supervisor", "site-999"), site_id=SITE_ID, now=NOW
        )
