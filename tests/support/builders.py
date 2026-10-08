"""Builders for domain objects under test.

Defaults are chosen so a test only states what it cares about. Note that `obligation()`
defaults to source_state=VERIFIED purely so resolution tests are readable -- the
*production* default is UNSOURCED, and test_resolver_unsourced.py asserts that.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aadesh_core.domain import (
    Citation,
    InvokedStage,
    Obligation,
    Provenance,
    SiteProfile,
    SourceState,
    StationReading,
)

FIXED_NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


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
