"""Pure trigger decision for a standing order.

This function answers one question: given a standing order and a stage-trip event, should the
machine be started? It is pure: it calls no clock, no Cedar, no store. Authorization is its own
step (the machine re-checks the recorded supervisor at fire time), and persistence is its own
step (the run claim makes a redelivery a no-op).

Refusals are each a closed reason with a human sentence, so every "no" is explainable without
reaching for a model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.stages import InvokedStage
from aadesh_core.standing_order.models import StandingOrder


@dataclass(frozen=True, slots=True)
class StageTripEvent:
    """The event a standing order may react to: an invocation, proved by the corpus.

    The event carries the order it came from, so the trigger fingerprint is computable and the
    call is not "does stage 3 fire?" but "does THIS invocation of stage 3 fire?". A bare
    integer would be too weak -- a revoked January invocation and a current October one would
    look identical.
    """

    invoked: InvokedStage
    site_id: str

    @property
    def order_doc_id(self) -> str:
        return self.invoked.order_doc_id

    @property
    def order_sha256(self) -> str:
        return self.invoked.order_sha256


@dataclass(frozen=True, slots=True)
class TriggerRefusal:
    """One reason the trigger must not fire."""

    code: str
    reason: str
    public: bool = True
    """If False, the reason is internal bookkeeping and must not be shown verbatim to a user."""


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    """The tri-state output of evaluate_trigger.

    Either the machine starts (fires=True), or it does not (fires=False) and exactly one
    refusal explains why. The fingerprint is available in both cases so a caller can record the
    event id regardless of outcome -- useful for audit and for idempotent run claiming.
    """

    fires: bool
    fingerprint: str
    refusal: TriggerRefusal | None

    @property
    def reason(self) -> str:
        if self.refusal is None:
            return "trigger matched: standing order fires"
        return self.refusal.reason

    def expect_fire(self) -> None:
        if not self.fires:
            raise RuntimeError(f"trigger did not fire: {self.refusal.code}: {self.refusal.reason}")


TRIGGER_REFUSALS = {
    "NOT_CURRENT_INVOCATION": (
        "The triggering invocation has been revoked. A revoked order is history, not a current "
        "stage, and it does not fire anything. This is the same rule everywhere in the corpus: "
        "a revoked invocation is evidence about the past, never cause for action."
    ),
    "WRONG_SITE": (
        "The triggering invocation is for a different site than the standing order names. A "
        "pre-commitment scoped to one site does not fire for another site's invocation."
    ),
    "WRONG_STAGE": (
        "The currently invoked stage does not match the standing order's trigger. An order that "
        "pre-commits to a specific trigger does not fire for a different stage."
    ),
    "NOT_YET_ACTIVE": (
        "The standing order is not yet active. It becomes active only after valid_from and only "
        "after the supervisor has signed it. Pre-committing is not the same as deploying."
    ),
    "EXPIRED": (
        "The standing order expired at its valid_until. A time-bounded pre-commitment does not "
        "survive past its window, and expiry is computed now, not by a timer that may not have "
        "run."
    ),
    "ALREADY_TRIGGERED": (
        "This standing order has already been triggered. A pre-commitment is spent on its first "
        "matched trigger; a later invocation requires a new signed order."
    ),
    "COMMITMENT_ALTERED": (
        "The standing order on record no longer matches the supervisor's signature. The signed "
        "fields do not hash to the stored commitment_hash, so the order is not trusted to fire."
    ),
}


def _refusal(code: str, *, public: bool = True) -> TriggerRefusal:
    return TriggerRefusal(code=code, reason=TRIGGER_REFUSALS[code], public=public)


def evaluate_trigger(
    *,
    order: StandingOrder,
    event: StageTripEvent,
    now: datetime,
) -> TriggerDecision:
    """Should this standing order fire, given this stage-trip event and the current time?

    Pure. Returns a TriggerDecision. The caller (the machine or its adapter) decides what to do
    with a firing -- including re-checking authorization and claiming the run.
    """
    fingerprint = order.compute_trigger_fingerprint(
        order_doc_id=event.order_doc_id,
        order_sha256=event.order_sha256,
    )

    # 1. The event itself must be current. A revoked invocation never fires anything.
    if not event.invoked.is_current:
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("NOT_CURRENT_INVOCATION")
        )

    # 2. The invocation must be for the same site the order is scoped to.
    if event.site_id != order.site_id:
        return TriggerDecision(fires=False, fingerprint=fingerprint, refusal=_refusal("WRONG_SITE"))

    # 3. The currently invoked stage must satisfy the trigger's match rule.
    if not order.trigger.evaluate(invoked_stage=event.invoked.stage):
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("WRONG_STAGE")
        )

    # 4. The order must be trusted: signed, and its fields still hash to the signed
    #    commitment.
    if not order.has_signed:
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("NOT_YET_ACTIVE")
        )

    if order.commitment_hash is None:
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("NOT_YET_ACTIVE")
        )

    if order.commitment_hash != order.compute_commitment_hash():
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("COMMITMENT_ALTERED")
        )

    # 5. The order must be in its live window now. Project the status from the clock rather than
    #    reading the stored string -- that is what makes expiry survive a missing timer.
    projected = _projected_status(order, now=now)

    if projected is StandingOrderStatus.EXPIRED:
        return TriggerDecision(fires=False, fingerprint=fingerprint, refusal=_refusal("EXPIRED"))

    # A standing order that has already been triggered (or completed) is spent. This check comes
    # before the "must be ACTIVE" check because a TRIGGERED/COMPLETED order projects to its own
    # status, not ACTIVE, and would otherwise be misread as NOT_YET_ACTIVE.
    if order.status in (StandingOrderStatus.TRIGGERED, StandingOrderStatus.COMPLETED):
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("ALREADY_TRIGGERED")
        )

    if projected is not StandingOrderStatus.ACTIVE:
        return TriggerDecision(
            fires=False, fingerprint=fingerprint, refusal=_refusal("NOT_YET_ACTIVE")
        )

    # 7. The status stored on the order must itself project to ACTIVE. A stale ACTIVE row on disk
    #    is not a permit -- project_status wins.
    if order.status is StandingOrderStatus.EXPIRED:
        return TriggerDecision(fires=False, fingerprint=fingerprint, refusal=_refusal("EXPIRED"))

    return TriggerDecision(fires=True, fingerprint=fingerprint, refusal=None)


def _projected_status(order: StandingOrder, *, now: datetime) -> StandingOrderStatus:
    from aadesh_core.standing_order.lifecycle import project_status

    return project_status(order, now=now)


def filter_firing_orders(
    *,
    orders: Sequence[StandingOrder],
    event: StageTripEvent,
    now: datetime,
) -> list[TriggerDecision]:
    """Evaluate every standing order against one event, returning only the ones that fire.

    Convenience for a resolver or a Step Functions choice state that needs "which orders, if
    any, react to this invocation?". Refusals for non-firing orders are kept in the decision so
    the caller can audit or log them; the caller filters on fires.
    """
    return [evaluate_trigger(order=order, event=event, now=now) for order in orders]
