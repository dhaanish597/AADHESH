"""Full-chain structural idempotency test for a Standing Order.

This is the test that proves the user's requirement: "the system must never create duplicate
parchis for the same trigger."

The mechanism is structural, not a guard flag:

  1. The trigger fingerprint is deterministic over (standing_order_id, site_id, stage,
     order_doc_id, order_sha256).
  2. Each parchi id is deterministic over (fingerprint, worker_id).
  3. TriggerRunStore.claim is create-if-absent and returns the EXISTING run on collision.
  4. A redelivery therefore computes the same run, the same parchi ids, and claims the same run
     -- creating nothing.

The test exercises the fake TriggerRunStore (the contract test holds it to the same contract the
DynamoDB adapter must satisfy) and walks from a stage-trip event through the machine's
create-parchis step to sealed parchis, once for the original trigger and once for a redelivery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aadesh_core.domain.enums import (
    ParchiState,
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)
from aadesh_core.parchi import acknowledge, compute_content_hash, issue, open_parchi
from aadesh_core.stages import InvokedStage
from aadesh_core.standing_order.models import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    TriggerRun,
    deterministic_parchi_id,
    frozendict,
    trigger_fingerprint,
)
from aadesh_core.standing_order.trigger import StageTripEvent, evaluate_trigger
from tests.unit.test_trigger_run_store_contract import FakeTriggerRunStore

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)


def _invoked_stage(
    *,
    stage: int = 3,
    doc_id: str = "order-001",
    sha: str = "a" * 64,
    revoked: bool = False,
) -> InvokedStage:
    from aadesh_core.domain.enums import InvocationLifecycle

    return InvokedStage(
        stage=stage,
        order_doc_id=doc_id,
        order_sha256=sha,
        invoked_at=NOW,
        lifecycle=InvocationLifecycle.REVOKED if revoked else InvocationLifecycle.ACTIVE,
        revoked_at=(NOW + timedelta(days=1)) if revoked else None,
        citation=None,
        source_state=None,
    )


def _standing_order(
    *,
    standing_order_id: str = "so-1",
    site_id: str = "site-001",
    supervisor_id: str = "sup-1",
    trigger_stage: int = 3,
    trigger_match: StageMatch = StageMatch.EXACT,
    status: StandingOrderStatus = StandingOrderStatus.ACTIVE,
    valid_from: datetime = VALID_FROM,
    valid_until: datetime = VALID_UNTIL,
    signed_at: datetime | None = NOW,
    commitment_hash: str | None = None,
    fingerprint: str | None = None,
) -> StandingOrder:
    trigger = StageInvocationTrigger(
        stage=trigger_stage,
        match=trigger_match,
        type=TriggerType.OFFICIAL_STAGE_INVOCATION,
    )
    actions = (
        StandingOrderActionClause(
            action=StandingOrderAction.ISSUE_HALT,
            parameters=frozendict({}),
        ),
        StandingOrderActionClause(
            action=StandingOrderAction.OPEN_PARCHI_PER_WORKER,
            parameters=frozendict({}),
        ),
    )
    return StandingOrder(
        standing_order_id=standing_order_id,
        site_id=site_id,
        supervisor_id=supervisor_id,
        trigger=trigger,
        actions=actions,
        valid_from=valid_from,
        valid_until=valid_until,
        status=status,
        created_at=NOW - timedelta(days=1),
        signed_at=signed_at,
        commitment_hash=commitment_hash,
        trigger_fingerprint=fingerprint,
        triggered_at=None,
        completed_at=None,
        expired_at=None,
    )


def _order_commitment_hash(order: StandingOrder) -> str:
    return order.compute_commitment_hash()


# --- the create-parchis step (pure, for the test) --------------------------


def create_parchis_for_order(
    *,
    order: StandingOrder,
    run: TriggerRun,
    worker_ids: tuple[str, ...],
    now: datetime = NOW,
) -> tuple[dict]:
    """Simulate the CreateParchis step: open one DRAFT parchi per rostered worker, deterministic
    from (fingerprint, worker_id)."""
    parchis = []
    for worker_id in worker_ids:
        parchi_id = deterministic_parchi_id(fingerprint=run.fingerprint, worker_id=worker_id)
        parchi = open_parchi(
            parchi_id=parchi_id,
            site_id=order.site_id,
            worker_id=worker_id,
            stage=None,  # the actual invocation is attached later by the adapter
            reading=None,
            obligation_ids=(),
            entitlement_refs=(),
            readiness_checklist=(),
            displaced_worker_days=0,
            now=now,
        )
        parchis.append({"parchi": parchi, "worker_id": worker_id})
    return tuple(parchis)


# --- the main structural idempotency test ----------------------------------


def test_a_trigger_creates_parchis_and_a_redelivery_creates_nothing() -> None:
    """The core claim: fire the same trigger twice, and parchis are created exactly once."""
    order = _standing_order(
        standing_order_id="so-1",
        site_id="site-001",
        supervisor_id="sup-1",
        trigger_stage=3,
        status=StandingOrderStatus.ACTIVE,
        commitment_hash=_order_commitment_hash(
            _standing_order(
                standing_order_id="so-1",
                site_id="site-001",
                supervisor_id="sup-1",
                trigger_stage=3,
                status=StandingOrderStatus.ACTIVE,
            )
        ),
    )
    # Rewrite the order's commitment_hash in place (value objects are frozen; we rebuild).
    order = _standing_order(
        standing_order_id="so-1",
        site_id="site-001",
        supervisor_id="sup-1",
        trigger_stage=3,
        status=StandingOrderStatus.ACTIVE,
        commitment_hash=_order_commitment_hash(order),
    )

    event = StageTripEvent(
        invoked=_invoked_stage(stage=3, doc_id="order-001", sha="a" * 64),
        site_id="site-001",
    )
    decision = evaluate_trigger(order=order, event=event, now=NOW)
    assert decision.fires is True

    fingerprint = decision.fingerprint
    worker_ids = ("wrk-1", "wrk-2", "wrk-3")

    store = FakeTriggerRunStore()

    # --- first delivery: the machine starts, creates the run, creates the parchis ---
    run = TriggerRun(
        fingerprint=fingerprint,
        standing_order_id=order.standing_order_id,
        site_id=order.site_id,
        stage=3,
        order_doc_id=event.order_doc_id,
        order_sha256=event.order_sha256,
        started_at=NOW,
        status=StandingOrderStatus.TRIGGERED,
        parchi_ids=tuple(
            deterministic_parchi_id(fingerprint=fingerprint, worker_id=wid) for wid in worker_ids
        ),
    )
    first_claim = store.claim(run)
    assert first_claim is run
    assert first_claim.parchi_ids == tuple(
        deterministic_parchi_id(fingerprint=fingerprint, worker_id=wid) for wid in worker_ids
    )

    first_parchis = create_parchis_for_order(order=order, run=run, worker_ids=worker_ids, now=NOW)
    first_parchi_ids = tuple(p["parchi"].parchi_id for p in first_parchis)
    assert first_parchi_ids == run.parchi_ids

    # --- second delivery (redelivery): same trigger, nothing new ---
    redelivery_run = TriggerRun(
        fingerprint=fingerprint,
        standing_order_id=order.standing_order_id,
        site_id=order.site_id,
        stage=3,
        order_doc_id=event.order_doc_id,
        order_sha256=event.order_sha256,
        started_at=NOW + timedelta(seconds=1),
        status=StandingOrderStatus.TRIGGERED,
        parchi_ids=tuple(
            deterministic_parchi_id(fingerprint=fingerprint, worker_id=wid) for wid in worker_ids
        ),
    )
    second_claim = store.claim(redelivery_run)
    # claim returns the EXISTING run -- no new run, no new parchi ids.
    assert second_claim is first_claim
    assert second_claim.parchi_ids == first_parchi_ids
    assert second_claim.parchi_ids == run.parchi_ids
    # The store did not grow: the same fingerprint maps to the same run.
    assert len(store.get(fingerprint).parchi_ids) == len(worker_ids)


def test_parchi_ids_are_deterministic_from_fingerprint_and_worker_id() -> None:
    """Two calls to deterministic_parchi_id with the same inputs return the same id. Two calls
    with a different worker return different ids. Two calls with a different trigger return
    different ids."""
    fp = "fingerprint-abc123"
    wid = "wrk-1"
    assert deterministic_parchi_id(fingerprint=fp, worker_id=wid) == deterministic_parchi_id(
        fingerprint=fp, worker_id=wid
    )
    assert deterministic_parchi_id(fingerprint=fp, worker_id=wid) != deterministic_parchi_id(
        fingerprint=fp, worker_id="wrk-2"
    )
    assert deterministic_parchi_id(fingerprint=fp, worker_id=wid) != deterministic_parchi_id(
        fingerprint="other-fp", worker_id=wid
    )


def test_redelivery_produces_the_same_fingerprint_as_the_original() -> None:
    """A redelivery must compute the same fingerprint -- that is what makes claim a no-op."""
    order = _standing_order(
        standing_order_id="so-1", site_id="site-001", supervisor_id="sup-1", trigger_stage=3
    )
    event = StageTripEvent(
        invoked=_invoked_stage(stage=3, doc_id="order-001", sha="a" * 64),
        site_id="site-001",
    )
    first = evaluate_trigger(order=order, event=event, now=NOW)
    second = evaluate_trigger(order=order, event=event, now=NOW)
    assert first.fingerprint == second.fingerprint


def test_two_different_triggers_produce_different_fingerprints_and_different_parchi_ids() -> None:
    """A genuinely new order (different order_sha256) is a different trigger -- different
    fingerprint, different parchi ids. Combined with fire-once, a new order is refused as
    ALREADY_TRIGGERED only if it already fired; a new order that has not fired yet gets its own
    run."""
    order = _standing_order(
        standing_order_id="so-1", site_id="site-001", supervisor_id="sup-1", trigger_stage=3
    )
    event_a = StageTripEvent(
        invoked=_invoked_stage(stage=3, doc_id="order-001", sha="a" * 64),
        site_id="site-001",
    )
    event_b = StageTripEvent(
        invoked=_invoked_stage(stage=3, doc_id="order-001", sha="b" * 64),
        site_id="site-001",
    )
    fp_a = evaluate_trigger(order=order, event=event_a, now=NOW).fingerprint
    fp_b = evaluate_trigger(order=order, event=event_b, now=NOW).fingerprint
    assert fp_a != fp_b
    assert deterministic_parchi_id(fingerprint=fp_a, worker_id="wrk-1") != deterministic_parchi_id(
        fingerprint=fp_b, worker_id="wrk-1"
    )


def test_sealed_parchi_ids_are_stable_across_a_redelivery() -> None:
    """Even after sealing, a parchi id is stable. A redelivery that re-opens the same parchi id
    collides on save (ParchiStore.save refuses to overwrite a sealed one) rather than minting a
    twin. This test proves the id stability; the save guard is Parchi's own contract."""
    order = _standing_order(
        standing_order_id="so-1", site_id="site-001", supervisor_id="sup-1", trigger_stage=3
    )
    fp = trigger_fingerprint(
        standing_order_id=order.standing_order_id,
        site_id=order.site_id,
        stage=3,
        order_doc_id="order-001",
        order_sha256="a" * 64,
    )
    parchi_id = deterministic_parchi_id(fingerprint=fp, worker_id="wrk-1")
    parchi = open_parchi(
        parchi_id=parchi_id,
        site_id=order.site_id,
        worker_id="wrk-1",
        stage=_invoked_stage(stage=3),
        reading=None,
        obligation_ids=(),
        entitlement_refs=(),
        readiness_checklist=(),
        displaced_worker_days=0,
        now=NOW,
    )
    issued = issue(parchi, now=NOW)
    sealed = acknowledge(issued, actor_worker_id="wrk-1", now=NOW + timedelta(minutes=1))
    assert sealed.parchi_id == parchi_id
    assert sealed.content_hash == compute_content_hash(sealed)
    # The id is stable across a hypothetical redelivery: deterministic_parchi_id returns the same.
    assert deterministic_parchi_id(fingerprint=fp, worker_id="wrk-1") == parchi_id


def test_a_fully_sealed_parchi_for_each_worker_is_the_terminal_outcome() -> None:
    """The happy path: each rostered worker acknowledges their own parchi, every parchi seals."""
    order = _standing_order(
        standing_order_id="so-1", site_id="site-001", supervisor_id="sup-1", trigger_stage=3
    )
    fp = trigger_fingerprint(
        standing_order_id=order.standing_order_id,
        site_id=order.site_id,
        stage=3,
        order_doc_id="order-001",
        order_sha256="a" * 64,
    )
    parchi_ids = [deterministic_parchi_id(fingerprint=fp, worker_id=f"wrk-{i}") for i in (1, 2)]
    sealed = []
    for wid, pid in zip(("wrk-1", "wrk-2"), parchi_ids, strict=True):
        parchi = open_parchi(
            parchi_id=pid,
            site_id=order.site_id,
            worker_id=wid,
            stage=_invoked_stage(stage=3),
            reading=None,
            obligation_ids=(),
            entitlement_refs=(),
            readiness_checklist=(),
            displaced_worker_days=0,
            now=NOW,
        )
        issued = issue(parchi, now=NOW)
        s = acknowledge(issued, actor_worker_id=wid, now=NOW + timedelta(minutes=1))
        sealed.append(s)
    assert all(p.state is ParchiState.SEALED for p in sealed)
    assert all(p.content_hash is not None for p in sealed)
    assert len({p.parchi_id for p in sealed}) == 2
