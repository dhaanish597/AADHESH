"""Pure lifecycle transitions and project_status for a StandingOrder.

These tests verify the lifecycle the user specified:

    DRAFT -> CONFIRMED -> ACTIVE -> TRIGGERED -> COMPLETED -> EXPIRED

with EXPIRED reachable from any non-terminal status once valid_until passes, and with
project_status computing the authoritative status from the clock rather than reading the stored
string -- which is what "not a frontend timer" has to mean to be worth claiming.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)
from aadesh_core.standing_order.lifecycle import (
    IllegalStandingOrderTransition,
    activate,
    complete,
    confirm,
    expire,
    fire,
    project_status,
)
from aadesh_core.standing_order.models import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    frozendict,
)

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)


def _order(
    *,
    status: StandingOrderStatus = StandingOrderStatus.DRAFT,
    valid_from: datetime = VALID_FROM,
    valid_until: datetime = VALID_UNTIL,
    signed_at: datetime | None = None,
    commitment_hash: str | None = None,
    triggered_at: datetime | None = None,
    completed_at: datetime | None = None,
    expired_at: datetime | None = None,
    supervisor_id: str = "sup-1",
    site_id: str = "site-001",
    trigger: StageInvocationTrigger | None = None,
    actions: tuple[StandingOrderActionClause, ...] | None = None,
    fingerprint: str | None = None,
) -> StandingOrder:
    from uuid import uuid4

    if trigger is None:
        trigger = StageInvocationTrigger(
            stage=3,
            match=StageMatch.EXACT,
            type=TriggerType.OFFICIAL_STAGE_INVOCATION,
        )
    if actions is None:
        actions = (
            StandingOrderActionClause(
                action=StandingOrderAction.ISSUE_HALT,
                parameters=frozendict({}),
            ),
        )
    return StandingOrder(
        standing_order_id=str(uuid4()),
        site_id=site_id,
        supervisor_id=supervisor_id,
        trigger=trigger,
        actions=actions,
        valid_from=valid_from,
        valid_until=valid_until,
        status=status,
        created_at=NOW,
        signed_at=signed_at,
        commitment_hash=commitment_hash,
        trigger_fingerprint=fingerprint,
        triggered_at=triggered_at,
        completed_at=completed_at,
        expired_at=expired_at,
    )


def test_confirm_moves_draft_to_confirmed_and_fixes_commitment():
    order = _order(status=StandingOrderStatus.DRAFT)
    confirmed = confirm(order, supervisor_id="sup-1", now=NOW)
    assert confirmed.status is StandingOrderStatus.CONFIRMED
    assert confirmed.signed_at == NOW
    assert confirmed.commitment_hash is not None
    assert len(confirmed.commitment_hash) == 64
    assert confirmed.commitment_hash == confirmed.compute_commitment_hash()


def test_confirm_rejects_wrong_supervisor():
    order = _order(status=StandingOrderStatus.DRAFT)
    with pytest.raises(IllegalStandingOrderTransition, match="only supervisor"):
        confirm(order, supervisor_id="sup-2", now=NOW)


def test_confirm_is_idempotent():
    order = _order(status=StandingOrderStatus.DRAFT)
    first = confirm(order, supervisor_id="sup-1", now=NOW)
    second = confirm(first, supervisor_id="sup-1", now=NOW)
    assert second is first  # with_commitment_hash is a no-op when hash already set


def test_activate_requires_now_at_or_after_valid_from():
    order = _order(status=StandingOrderStatus.CONFIRMED, valid_from=VALID_FROM)
    before = VALID_FROM - timedelta(seconds=1)
    with pytest.raises(IllegalStandingOrderTransition, match="not yet valid"):
        activate(order, now=before)
    active = activate(order, now=VALID_FROM)
    assert active.status is StandingOrderStatus.ACTIVE


def test_fire_moves_active_to_triggered_and_records_fingerprint():
    order = _order(status=StandingOrderStatus.ACTIVE, fingerprint="abc123")
    fired = fire(order, now=NOW)
    assert fired.status is StandingOrderStatus.TRIGGERED
    assert fired.triggered_at == NOW
    assert fired.trigger_fingerprint == "abc123"


def test_fire_refuses_an_expired_order():
    order = _order(
        status=StandingOrderStatus.ACTIVE,
        valid_from=NOW - timedelta(hours=4),
        valid_until=NOW - timedelta(seconds=1),
        fingerprint="abc123",
    )
    with pytest.raises(IllegalStandingOrderTransition, match="expired"):
        fire(order, now=NOW)


def test_complete_moves_triggered_to_completed():
    order = _order(status=StandingOrderStatus.TRIGGERED, triggered_at=NOW)
    completed = complete(order, now=NOW + timedelta(minutes=1))
    assert completed.status is StandingOrderStatus.COMPLETED
    assert completed.completed_at == NOW + timedelta(minutes=1)


def test_expire_reaches_expired_from_any_non_terminal_status():
    for status in (
        StandingOrderStatus.DRAFT,
        StandingOrderStatus.CONFIRMED,
        StandingOrderStatus.ACTIVE,
        StandingOrderStatus.TRIGGERED,
        StandingOrderStatus.COMPLETED,
    ):
        order = _order(status=status, expired_at=None)
        expired = expire(order, now=NOW + timedelta(days=1))
        assert expired.status is StandingOrderStatus.EXPIRED
        assert expired.expired_at == NOW + timedelta(days=1)


def test_expire_refuses_an_already_expired_order():
    order = _order(status=StandingOrderStatus.EXPIRED, expired_at=NOW)
    with pytest.raises(IllegalStandingOrderTransition, match="already"):
        expire(order, now=NOW + timedelta(days=1))


def test_project_status_returns_expired_once_valid_until_passes():
    order = _order(status=StandingOrderStatus.ACTIVE)
    assert (
        project_status(order, now=VALID_UNTIL - timedelta(seconds=1)) is StandingOrderStatus.ACTIVE
    )
    assert project_status(order, now=VALID_UNTIL) is StandingOrderStatus.EXPIRED
    assert project_status(order, now=VALID_UNTIL + timedelta(days=1)) is StandingOrderStatus.EXPIRED


def test_project_status_marks_confirmed_order_active_once_window_opens():
    order = _order(
        status=StandingOrderStatus.CONFIRMED,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
    )
    assert (
        project_status(order, now=VALID_FROM - timedelta(seconds=1))
        is StandingOrderStatus.CONFIRMED
    )
    assert project_status(order, now=VALID_FROM) is StandingOrderStatus.ACTIVE


def test_project_status_before_valid_from_keeps_draft_as_draft():
    order = _order(status=StandingOrderStatus.DRAFT)
    assert project_status(order, now=NOW) is StandingOrderStatus.DRAFT


def test_project_status_wins_over_stale_persisted_active():
    """A row that still says ACTIVE cannot fire past valid_until even if no sweeper ran.

    This is the direct test of "not a frontend timer." The stored status is ACTIVE, but
    project_status returns EXPIRED the moment now >= valid_until.
    """
    order = _order(
        status=StandingOrderStatus.ACTIVE,
        valid_from=NOW - timedelta(hours=4),
        valid_until=NOW - timedelta(seconds=1),
    )
    assert order.status is StandingOrderStatus.ACTIVE
    assert project_status(order, now=NOW) is StandingOrderStatus.EXPIRED


def test_project_status_on_completed_order_still_expires():
    """COMPLETED -> EXPIRED is reachable: a completed order still expires past valid_until."""
    order = _order(
        status=StandingOrderStatus.COMPLETED,
        valid_from=NOW - timedelta(hours=4),
        valid_until=NOW - timedelta(seconds=1),
    )
    assert project_status(order, now=NOW) is StandingOrderStatus.EXPIRED


def test_order_must_have_nonempty_actions():
    from uuid import uuid4

    with pytest.raises(ValueError, match="at least one action"):
        StandingOrder(
            standing_order_id=str(uuid4()),
            site_id="site-001",
            supervisor_id="sup-1",
            trigger=StageInvocationTrigger(stage=3),
            actions=(),
            valid_from=VALID_FROM,
            valid_until=VALID_UNTIL,
            status=StandingOrderStatus.DRAFT,
            created_at=NOW,
        )


def test_order_rejects_valid_from_at_or_after_valid_until():
    from uuid import uuid4

    with pytest.raises(ValueError, match="valid_from must precede"):
        StandingOrder(
            standing_order_id=str(uuid4()),
            site_id="site-001",
            supervisor_id="sup-1",
            trigger=StageInvocationTrigger(stage=3),
            actions=(
                StandingOrderActionClause(
                    action=StandingOrderAction.ISSUE_HALT, parameters=frozendict({})
                ),
            ),
            valid_from=VALID_UNTIL,
            valid_until=VALID_FROM,
            status=StandingOrderStatus.DRAFT,
            created_at=NOW,
        )


def test_order_rejects_naive_timestamps():
    from uuid import uuid4

    with pytest.raises(ValueError, match="timezone-aware"):
        StandingOrder(
            standing_order_id=str(uuid4()),
            site_id="site-001",
            supervisor_id="sup-1",
            trigger=StageInvocationTrigger(stage=3),
            actions=(
                StandingOrderActionClause(
                    action=StandingOrderAction.ISSUE_HALT, parameters=frozendict({})
                ),
            ),
            valid_from=datetime(2026, 10, 8, 10, 0),  # naive
            valid_until=VALID_UNTIL,
            status=StandingOrderStatus.DRAFT,
            created_at=NOW,
        )
