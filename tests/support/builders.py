"""Builders for domain objects under test.

Defaults are chosen so a test only states what it cares about. Note that `obligation()`
defaults to source_state=VERIFIED purely so resolution tests are readable -- the
*production* default is UNSOURCED, and test_resolver_unsourced.py asserts that.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aadesh_core.domain import (
    Citation,
    InvokedStage,
    Obligation,
    Provenance,
    SiteProfile,
    SourceState,
    StationReading,
)
from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)
from aadesh_core.standing_order.models import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    frozendict,
)

FIXED_NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)


def citation(**over: Any) -> Citation:
    return Citation(
        **{
            "source_doc": "test-order",
            "page": 4,
            "quote": "verbatim text from a hashed source document",
            **over,
        }
    )


def obligation(**over: Any) -> Obligation:
    return Obligation(
        **{
            "obligation_id": "test-ob-01",
            "entity_types": ("construction_site",),
            "triggers_at_stage": 3,
            "label": "Test obligation",
            "field": "has_dust_generating_activity",
            "operator": "eq",
            "value": True,
            "citation": citation(),
            "issues_parchi": True,
            "worker_entitlement_ref": None,
            "source_state": SourceState.VERIFIED,
            **over,
        }
    )


def site(**over: Any) -> SiteProfile:
    return SiteProfile(
        **{
            "site_id": "site-001",
            "entity_type": "construction_site",
            "nearest_station_id": "station-001",
            "facts": {"has_dust_generating_activity": True},
            **over,
        }
    )


def invoked_stage(**over: Any) -> InvokedStage:
    return InvokedStage(
        **{
            "stage": 3,
            "order_doc_id": "test-order",
            "order_sha256": "a" * 64,
            "invoked_at": FIXED_NOW,
            **over,
        }
    )


def reading(**over: Any) -> StationReading:
    return StationReading(
        **{
            "station_id": "station-001",
            "parameter": "aqi",
            "value": 1.0,
            "observed_at": FIXED_NOW,
            "ingested_at": FIXED_NOW,
            "provenance": Provenance.SYNTHETIC,
            **over,
        }
    )


def standing_order(
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
