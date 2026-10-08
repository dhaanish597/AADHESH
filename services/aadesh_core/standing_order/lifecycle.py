"""Pure StandingOrder lifecycle transitions.

Every transition returns a NEW standing order. Nothing here mutates. The stored `status` is
decorative -- the authoritative status at any instant is computed by `project_status`, which is
what the trigger path and the machine guard on.

Lifecycle:

    DRAFT ──confirm──▶ CONFIRMED ──activate──▶ ACTIVE ──fire──▶ TRIGGERED ──complete──▶ COMPLETED
      │                  │                    │               │                   │
      └──────────────────┴────────────────────┴───────────────┴───────────────────┴──▶ EXPIRED

EXPIRED is reachable from any non-terminal status the moment valid_until passes -- including
COMPLETED -- because expiry is a wall-clock property, not a machine step.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import StandingOrder


class IllegalStandingOrderTransition(ValueError):
    """An attempt to move a standing order through a transition its lifecycle forbids."""


def _require_status(order: StandingOrder, expected: StandingOrderStatus, action: str) -> None:
    if order.status is not expected:
        raise IllegalStandingOrderTransition(
            f"Cannot {action} standing order {order.standing_order_id}: it is "
            f"{order.status.value!r}, and {action} requires {expected.value!r}."
        )


def confirm(
    order: StandingOrder,
    *,
    supervisor_id: str,
    now: datetime,
) -> StandingOrder:
    """DRAFT -> CONFIRMED, or a no-op re-confirm of an already CONFIRMED order.

    The named supervisor signs, and the commitment is fixed. The commitment_hash is computed
    over the signed fields at this point, same shape as the Parchi.content_hash convention:
    evidence that can be edited after signing is not a pre-commitment.

    Re-signing a CONFIRMED order is a no-op: the hash is already set, and re-computing it
    would change the hash only if the fields changed, which they have not. This is what makes
    a redelivered confirm idempotent rather than a rehash.
    """
    if order.status is StandingOrderStatus.CONFIRMED:
        # Re-confirm: idempotent no-op. Only the original supervisor may re-confirm.
        if order.supervisor_id != supervisor_id:
            raise IllegalStandingOrderTransition(
                f"Cannot re-confirm standing order {order.standing_order_id}: only supervisor "
                f"{order.supervisor_id!r} may sign it, not {supervisor_id!r}."
            )
        return order
    _require_status(order, StandingOrderStatus.DRAFT, "confirm")
    if order.supervisor_id != supervisor_id:
        raise IllegalStandingOrderTransition(
            f"Cannot confirm standing order {order.standing_order_id}: only supervisor "
            f"{order.supervisor_id!r} may sign it, not {supervisor_id!r}."
        )
    signed = replace(order, status=StandingOrderStatus.CONFIRMED, signed_at=now)
    return signed.with_commitment_hash()


def activate(order: StandingOrder, *, now: datetime) -> StandingOrder:
    """CONFIRMED -> ACTIVE, but only once the effective window has opened."""
    _require_status(order, StandingOrderStatus.CONFIRMED, "activate")
    if now < order.valid_from:
        raise IllegalStandingOrderTransition(
            f"Cannot activate standing order {order.standing_order_id} at {now.isoformat()}: "
            f"it is not yet valid. It becomes active at {order.valid_from.isoformat()}."
        )
    return replace(order, status=StandingOrderStatus.ACTIVE)


def fire(order: StandingOrder, *, now: datetime) -> StandingOrder:
    """ACTIVE -> TRIGGERED. The machine is started.

    `now` must already be in the live window. The machine is responsible for anything that
    happens after -- parchi creation, acknowledgement, sealing and audit -- and for persisting
    the outcome. This function is pure: it records the fact of firing and nothing else.
    """
    _require_status(order, StandingOrderStatus.ACTIVE, "fire")
    if now >= order.valid_until:
        raise IllegalStandingOrderTransition(
            f"Cannot fire standing order {order.standing_order_id} at {now.isoformat()}: "
            f"it expired at {order.valid_until.isoformat()}."
        )
    return replace(
        order,
        status=StandingOrderStatus.TRIGGERED,
        triggered_at=now,
        trigger_fingerprint=order.trigger_fingerprint,
    )


def complete(order: StandingOrder, *, now: datetime) -> StandingOrder:
    """TRIGGERED -> COMPLETED. The machine reached Audit and reported its outcome."""
    _require_status(order, StandingOrderStatus.TRIGGERED, "complete")
    return replace(order, status=StandingOrderStatus.COMPLETED, completed_at=now)


def expire(
    order: StandingOrder,
    *,
    now: datetime,
    reason: str = "valid_until passed",
) -> StandingOrder:
    """Any non-terminal status -> EXPIRED, with an optional human reason.

    EXPIRED is reachable from any status except EXPIRED itself -- including COMPLETED -- because
    expiry is a wall-clock property, not a machine step. A completed order still expires past
    its valid_until.
    """
    if order.status is StandingOrderStatus.EXPIRED:
        raise IllegalStandingOrderTransition(
            f"Cannot expire standing order {order.standing_order_id}: it is already "
            f"{order.status.value!r}."
        )
    return replace(order, status=StandingOrderStatus.EXPIRED, expired_at=now)


def project_status(
    order: StandingOrder,
    *,
    now: datetime,
) -> StandingOrderStatus:
    """What the status MUST be at `now`, regardless of what was persisted.

    This is the load-bearing function behind "not a frontend timer". A row that still says
    ACTIVE cannot fire past valid_until even if no sweeper ever ran, because the trigger path
    and the machine guard on this, not on the stored string.

    Order of evaluation matters: expiry is a wall-clock property that wins over everything else.
    A CONFIRMED order whose window has opened projects to ACTIVE; a DRAFT stays DRAFT until
    signed; a TRIGGERED/COMPLETED/EXPIRED order projects to itself.
    """
    if now >= order.valid_until:
        return StandingOrderStatus.EXPIRED
    # A confirmed order whose window has opened is active, regardless of what the stored status
    # says (a stale ACTIVE row is also fine -- project_status agrees).
    if order.status is StandingOrderStatus.CONFIRMED and now >= order.valid_from:
        return StandingOrderStatus.ACTIVE
    return order.status
