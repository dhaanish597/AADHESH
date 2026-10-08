"""Trigger evaluation tests for a StandingOrder.

These cover the seven cases the user asked for, plus two additions the design flagged as
necessary: NOT_CURRENT_INVOCATION (a revoked invocation must never fire) and
COMMITMENT_ALTERED (a stored order whose fields no longer hash to the signed commitment must not
fire, otherwise "signed" is decoration).

Idempotency is tested structurally: the fingerprint is deterministic, and a redelivered trigger
computes the same decision, the same fingerprint, and therefore the same parchi ids. The real
"no duplicate parchis" guarantee is the TriggerRunStore.claim contract, which gets its own test
in test_trigger_run_store_contract.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)
from aadesh_core.stages import InvokedStage
from aadesh_core.standing_order.models import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    frozendict,
    trigger_fingerprint,
)
from aadesh_core.standing_order.trigger import (
    StageTripEvent,
    TriggerDecision,
    evaluate_trigger,
    filter_firing_orders,
)

FIXED_NOW_STANDING = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
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
        invoked_at=FIXED_NOW_STANDING,
        lifecycle=InvocationLifecycle.REVOKED if revoked else InvocationLifecycle.ACTIVE,
        revoked_at=(FIXED_NOW_STANDING + timedelta(days=1)) if revoked else None,
        citation=None,
        source_state=None,
    )


def _order(
    *,
    status: StandingOrderStatus = StandingOrderStatus.ACTIVE,
    valid_from: datetime = VALID_FROM,
    valid_until: datetime = VALID_UNTIL,
    signed_at: datetime | None = FIXED_NOW_STANDING,
    commitment_hash: str | None = None,
    triggered_at: datetime | None = None,
    completed_at: datetime | None = None,
    expired_at: datetime | None = None,
    supervisor_id: str = "sup-1",
    site_id: str = "site-001",
    trigger_stage: int = 3,
    trigger_match: StageMatch = StageMatch.EXACT,
    fingerprint: str | None = None,
    actions: tuple[StandingOrderActionClause, ...] | None = None,
) -> StandingOrder:
    from uuid import uuid4

    if actions is None:
        actions = (
            StandingOrderActionClause(
                action=StandingOrderAction.ISSUE_HALT,
                parameters=frozendict({}),
            ),
        )
    trigger = StageInvocationTrigger(
        stage=trigger_stage,
        match=trigger_match,
        type=TriggerType.OFFICIAL_STAGE_INVOCATION,
    )
    so = StandingOrder(
        standing_order_id=str(uuid4()),
        site_id=site_id,
        supervisor_id=supervisor_id,
        trigger=trigger,
        actions=actions,
        valid_from=valid_from,
        valid_until=valid_until,
        status=status,
        created_at=FIXED_NOW_STANDING,
        signed_at=signed_at,
        commitment_hash=commitment_hash,
        trigger_fingerprint=fingerprint,
        triggered_at=triggered_at,
        completed_at=completed_at,
        expired_at=expired_at,
    )
    # A signed order must have a commitment_hash for the trigger to trust it.
    if so.has_signed and so.commitment_hash is None:
        rebuilt = {f: getattr(so, f) for f in so.__dataclass_fields__}
        rebuilt["commitment_hash"] = so.compute_commitment_hash()
        so = StandingOrder(**rebuilt)
    return so


def _event(
    *,
    invoked_stage: InvokedStage,
    site_id: str = "site-001",
) -> StageTripEvent:
    return StageTripEvent(invoked=invoked_stage, site_id=site_id)


def _decision(*, order: StandingOrder, event: StageTripEvent) -> TriggerDecision:
    return evaluate_trigger(order=order, event=event, now=FIXED_NOW_STANDING)


# --- valid trigger ---------------------------------------------------------


def test_valid_trigger_fires():
    order = _order(status=StandingOrderStatus.ACTIVE)
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is True
    assert decision.refusal is None
    assert decision.reason == "trigger matched: standing order fires"
    assert len(decision.fingerprint) == 64


def test_valid_trigger_fires_for_at_or_above_match():
    """The corpus rule: a Stage III order fires when Stage IV is invoked (at_or_above)."""
    order = _order(
        status=StandingOrderStatus.ACTIVE,
        trigger_stage=3,
        trigger_match=StageMatch.AT_OR_ABOVE,
    )
    event = _event(invoked_stage=_invoked_stage(stage=4))
    decision = _decision(order=order, event=event)
    assert decision.fires is True


def test_exact_trigger_does_not_fire_for_a_higher_stage():
    """EXACT: Stage III order must NOT fire when Stage IV is invoked."""
    order = _order(
        status=StandingOrderStatus.ACTIVE,
        trigger_stage=3,
        trigger_match=StageMatch.EXACT,
    )
    event = _event(invoked_stage=_invoked_stage(stage=4))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "WRONG_STAGE"


# --- expired order ---------------------------------------------------------


def test_expired_order_does_not_fire():
    order = _order(
        status=StandingOrderStatus.ACTIVE,
        valid_until=FIXED_NOW_STANDING - timedelta(seconds=1),
    )
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "EXPIRED"


def test_order_expired_at_valid_until_does_not_fire():
    """Boundary: now == valid_until is expired."""
    order = _order(status=StandingOrderStatus.ACTIVE, valid_until=FIXED_NOW_STANDING)
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "EXPIRED"


# --- wrong site ------------------------------------------------------------


def test_wrong_site_does_not_fire():
    order = _order(site_id="site-001")
    event = _event(invoked_stage=_invoked_stage(stage=3), site_id="site-999")
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "WRONG_SITE"


# --- wrong stage -----------------------------------------------------------


def test_wrong_stage_does_not_fire():
    order = _order(trigger_stage=3)
    event = _event(invoked_stage=_invoked_stage(stage=4))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "WRONG_STAGE"


def test_wrong_stage_does_not_fire_for_lower_stage():
    order = _order(trigger_stage=3)
    event = _event(invoked_stage=_invoked_stage(stage=2))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "WRONG_STAGE"


# --- unauthorized supervisor -------------------------------------------------


def test_unauthorized_supervisor_block_is_authorization_step_not_trigger():
    """Trigger evaluation does not check the supervisor -- that is the Authorize step's job.

    This test asserts the shape: evaluate_trigger never rejects on supervisor identity. The
    authorization re-check happens in Authorize (machine.py) and at Cedar. A supervisor
    reassigned between signing and firing should be rejected there, not here, so no parchi is
    created to clean up.
    """
    order = _order(supervisor_id="sup-1", status=StandingOrderStatus.ACTIVE)
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    # Not refused by trigger evaluation. Authorization is separate.
    assert decision.fires is True
    assert decision.refusal is None


# --- repeated trigger -----------------------------------------------------


def test_already_triggered_order_does_not_fire_again():
    order = _order(
        status=StandingOrderStatus.TRIGGERED,
        triggered_at=FIXED_NOW_STANDING - timedelta(minutes=1),
    )
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "ALREADY_TRIGGERED"


def test_completed_order_does_not_fire_again():
    order = _order(status=StandingOrderStatus.COMPLETED, completed_at=FIXED_NOW_STANDING)
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "ALREADY_TRIGGERED"


# --- idempotency ----------------------------------------------------------


def test_same_trigger_computes_same_fingerprint_twice():
    """Idempotency is structural: the fingerprint is deterministic over the trigger identity."""
    order = _order(status=StandingOrderStatus.ACTIVE)
    event = _event(invoked_stage=_invoked_stage(stage=3))
    first = _decision(order=order, event=event)
    second = _decision(order=order, event=event)
    assert first.fingerprint == second.fingerprint
    assert first.fires == second.fires


def test_fingerprint_includes_order_sha256_so_different_orders_are_different_triggers():
    """A different November order invoking the same stage is a different trigger."""
    same_stage, different_order = "a" * 64, "b" * 64
    fp_a = trigger_fingerprint(
        standing_order_id="so-1",
        site_id="site-001",
        stage=3,
        order_doc_id="order-001",
        order_sha256=same_stage,
    )
    fp_b = trigger_fingerprint(
        standing_order_id="so-1",
        site_id="site-001",
        stage=3,
        order_doc_id="order-001",
        order_sha256=different_order,
    )
    assert fp_a != fp_b


# --- revoked invocation ----------------------------------------------------


def test_revoked_invocation_does_not_fire():
    """NOT_CURRENT_INVOCATION: a revoked Stage III must not fire anything.

    This is the same rule everywhere in the corpus: a revoked invocation is history, not cause
    for action. Without this check, January's revoked Stage III would keep enforcing in October.
    """
    revoked = _invoked_stage(stage=3, revoked=True)
    order = _order(status=StandingOrderStatus.ACTIVE)
    event = _event(invoked_stage=revoked, site_id="site-001")
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "NOT_CURRENT_INVOCATION"


# --- altered commitment ----------------------------------------------------


def test_altered_commitment_does_not_fire():
    """COMMITMENT_ALTERED: if the stored fields no longer hash to the signed commitment_hash,
    the order does not fire. Otherwise 'signed' is decoration."""
    order = _order(
        status=StandingOrderStatus.ACTIVE,
        commitment_hash="0" * 64,  # deliberately wrong
    )
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "COMMITMENT_ALTERED"


def test_unsigned_order_does_not_fire():
    order = _order(status=StandingOrderStatus.CONFIRMED, signed_at=None, commitment_hash=None)
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decision = _decision(order=order, event=event)
    assert decision.fires is False
    assert decision.refusal is not None
    assert decision.refusal.code == "NOT_YET_ACTIVE"


# --- filter_firing_orders -------------------------------------------------


def test_filter_returns_only_firing_orders():
    firing = _order(status=StandingOrderStatus.ACTIVE)
    not_firing = _order(
        status=StandingOrderStatus.EXPIRED, valid_until=FIXED_NOW_STANDING - timedelta(seconds=1)
    )
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decisions = filter_firing_orders(
        orders=[firing, not_firing], event=event, now=FIXED_NOW_STANDING
    )
    firing_decisions = [d for d in decisions if d.fires]
    assert len(firing_decisions) == 1
    assert firing_decisions[0].fingerprint == decisions[0].fingerprint


def test_filter_may_return_empty_list():
    order = _order(
        status=StandingOrderStatus.EXPIRED, valid_until=FIXED_NOW_STANDING - timedelta(seconds=1)
    )
    event = _event(invoked_stage=_invoked_stage(stage=3))
    decisions = filter_firing_orders(orders=[order], event=event, now=FIXED_NOW_STANDING)
    assert not any(d.fires for d in decisions)
