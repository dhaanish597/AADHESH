"""The trigger fingerprint is the chokepoint that makes duplicate parchis unrepresentable."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from aadesh_adapters.store.memory_standing_order import (
    InMemoryStandingOrderStore,
    InMemoryTriggerRunStore,
)
from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import TriggerRun
from tests.support.builders import standing_order

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def run(*, fingerprint="fp-1", parchi_ids=("parchi-001",)) -> TriggerRun:
    """`TriggerRun.__post_init__` refuses an empty `parchi_ids`, so the default is non-empty."""
    return TriggerRun(
        fingerprint=fingerprint,
        standing_order_id="so-1",
        site_id="example-piling-site",
        stage=3,
        order_doc_id="order-001",
        order_sha256="a" * 64,
        started_at=NOW,
        status=StandingOrderStatus.TRIGGERED,
        parchi_ids=tuple(parchi_ids),
    )


def test_claim_creates_when_absent() -> None:
    store = InMemoryTriggerRunStore()
    claimed = store.claim(run())
    assert claimed.fingerprint == "fp-1"
    assert store.get("fp-1") is not None


def test_claim_returns_the_existing_run_and_does_not_overwrite() -> None:
    """This is the whole contract. A redelivered trigger must not mint a second set."""
    store = InMemoryTriggerRunStore()
    store.claim(run(parchi_ids=("parchi-001",)))
    second = store.claim(run(parchi_ids=("parchi-999",)))
    assert second.parchi_ids == ("parchi-001",), "claim overwrote an existing run"


def test_complete_is_idempotent() -> None:
    store = InMemoryTriggerRunStore()
    store.claim(run())
    store.complete("fp-1", completed_at=NOW)
    first = store.get("fp-1")
    store.complete("fp-1", completed_at=NOW)
    assert store.get("fp-1").completed_at == first.completed_at


def test_complete_on_an_unknown_fingerprint_raises() -> None:
    store = InMemoryTriggerRunStore()
    with pytest.raises(KeyError):
        store.complete("no-such-fingerprint")


def test_standing_order_round_trips() -> None:
    store = InMemoryStandingOrderStore()
    order = standing_order()
    store.save(order)
    assert store.get(order.standing_order_id) == order


def test_for_site_returns_only_that_sites_orders() -> None:
    store = InMemoryStandingOrderStore()
    mine = standing_order(site_id="example-piling-site")
    theirs = standing_order(site_id="some-other-site")
    store.save(mine)
    store.save(theirs)
    assert [o.standing_order_id for o in store.for_site("example-piling-site")] == [
        mine.standing_order_id
    ]


def test_save_replaces_an_order_under_the_same_id() -> None:
    """DRAFT -> CONFIRMED is a legitimate replace of the same id, and the store must allow it."""
    store = InMemoryStandingOrderStore()
    order = standing_order(status=StandingOrderStatus.DRAFT, signed_at=None)
    store.save(order)
    store.save(replace(order, status=StandingOrderStatus.CONFIRMED, signed_at=NOW))
    assert store.get(order.standing_order_id).status is StandingOrderStatus.CONFIRMED
