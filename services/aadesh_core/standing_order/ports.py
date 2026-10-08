"""Persistence ports for the Standing Orders subsystem.

A StandingOrder is a pre-commitment, not an autonomous agent. The persistence layer is therefore
narrow: stores are queried for the order and its run, and the only write that matters for
idempotency is `TriggerRunStore.claim`, which is create-if-absent and MUST return the existing
run rather than raising on a collision.

No boto3, no DynamoDB types, no AWS names here. The protocols are satisfied by adapters; the
fingerprint-based contract is what makes "no duplicate parchis" structural rather than a guard
flag.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from aadesh_core.standing_order.models import StandingOrder, TriggerRun


@runtime_checkable
class StandingOrderStore(Protocol):
    """Where standing orders live. Thin, forward-only, keyed by standing_order_id."""

    def get(self, standing_order_id: str) -> StandingOrder | None:
        """Load a standing order by id, or None if it does not exist."""
        ...

    def save(self, order: StandingOrder) -> None:
        """Persist a standing order. MUST reject overwriting a different version of the same id
        unless the caller explicitly means to replace it (e.g. a DRAFT -> CONFIRMED transition).
        """
        ...

    def for_site(self, site_id: str) -> Sequence[StandingOrder]:
        """All standing orders scoped to one site, newest first is not required."""
        ...


@runtime_checkable
class TriggerRunStore(Protocol):
    """Where trigger runs live, keyed on the trigger fingerprint.

    This is the single chokepoint that makes duplicate parchis unrepresentable. A redelivery of
    the same trigger calls `claim`; if a run already exists, `claim` returns the existing one
    and creates nothing. The parchi ids are deterministic from (fingerprint, worker_id), so even
    a bypass can only overwrite an identical draft, not mint a twin.
    """

    def claim(self, run: TriggerRun) -> TriggerRun:
        """Create-if-absent. MUST return the EXISTING run when one is present and MUST NOT
        overwrite it. The returned run is the source of truth for the parchi ids that were (or
        will be) created for this trigger.
        """
        ...

    def get(self, fingerprint: str) -> TriggerRun | None:
        """Load a trigger run by its fingerprint, or None."""
        ...

    def complete(self, fingerprint: str, *, completed_at: datetime | None = None) -> None:
        """Mark a run COMPLETED, recording the audit outcome. Idempotent -- a second call is a
        no-op, not a re-run.
        """
        ...
