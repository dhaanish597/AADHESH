"""In-memory Standing Orders persistence. The reference for the DynamoDB adapters.

`TriggerRunStore.claim` is create-if-absent and returns the EXISTING run on a collision. It
does not raise. Raising would push the redelivery decision back onto the caller, and the
caller is a Step Functions retry that has no way to make it.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import StandingOrder, TriggerRun


class InMemoryStandingOrderStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: dict[str, StandingOrder] = {}

    def get(self, standing_order_id: str) -> StandingOrder | None:
        with self._lock:
            return self._orders.get(standing_order_id)

    def save(self, order: StandingOrder) -> None:
        with self._lock:
            self._orders[order.standing_order_id] = order

    def for_site(self, site_id: str) -> Sequence[StandingOrder]:
        with self._lock:
            return tuple(o for o in self._orders.values() if o.site_id == site_id)


class InMemoryTriggerRunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, TriggerRun] = {}

    def claim(self, run: TriggerRun) -> TriggerRun:
        with self._lock:
            existing = self._runs.get(run.fingerprint)
            if existing is not None:
                return existing
            self._runs[run.fingerprint] = run
            return run

    def get(self, fingerprint: str) -> TriggerRun | None:
        with self._lock:
            return self._runs.get(fingerprint)

    def complete(self, fingerprint: str, *, completed_at: datetime | None = None) -> None:
        with self._lock:
            existing = self._runs.get(fingerprint)
            if existing is None:
                raise KeyError(f"No trigger run for fingerprint {fingerprint!r}.")
            if existing.completed_at is not None:
                return
            self._runs[fingerprint] = replace(
                existing,
                status=StandingOrderStatus.COMPLETED,
                completed_at=completed_at or datetime.now(UTC),
            )
