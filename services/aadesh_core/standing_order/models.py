"""Value objects for the Aadesh Standing Orders subsystem.

A StandingOrder is a signed, narrow, time-bounded pre-commitment -- not a general
autonomous-agent permission. The shape enforces the narrowness:

  * one site and one trigger are singular fields, so a multi-site or multi-trigger order is
    unrepresentable rather than rejected;
  * actions is a non-empty tuple drawn from a closed enum (StandingOrderAction);
  * valid_until is required and is always present;
  * no field anywhere in this module expresses a prompt, instruction, script, code or template.

The lifecycle is recorded alongside the order as bookkeeping; the authoritative status at any
instant is computed by `project_status`, not read from the stored string.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)

StandingOrderId = str
"""A UUID4, minted at creation and never reused."""


def trigger_fingerprint(
    *,
    standing_order_id: str,
    site_id: str,
    stage: int,
    order_doc_id: str,
    order_sha256: str,
) -> str:
    """Deterministic dedupe key for one invocation of one standing order.

    Two redeliveries of the same trigger must not mint duplicate parchis. The fingerprint is
    the SHA-256 over the tuple that identifies a trigger event. It includes order_sha256 so a
    different November order invoking the same stage is a different trigger.
    """
    canonical = "\0".join(
        (
            standing_order_id,
            site_id,
            str(stage),
            order_doc_id,
            order_sha256,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def deterministic_parchi_id(*, fingerprint: str, worker_id: str) -> str:
    """A parchi id derived from the trigger, not minted from a counter.

    Two executions of the same trigger compute the same ids and therefore collide on save;
    combined with TriggerRunStore.claim returning the existing run, duplicate parchis become
    unrepresentable rather than checked-for.
    """
    raw = f"{fingerprint}:{worker_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"parchi-{digest[:32]}"


@dataclass(frozen=True, slots=True)
class StageInvocationTrigger:
    """The single trigger a standing order subscribes to.

    `match` controls whether the invoked stage must equal the trigger stage (EXACT) or be at
    or above it (AT_OR_ABOVE). This makes the corpus's continuation rule explicit in the signed
    order rather than implicit in resolver logic.
    """

    stage: int
    match: StageMatch = StageMatch.EXACT
    type: TriggerType = TriggerType.OFFICIAL_STAGE_INVOCATION

    def __post_init__(self) -> None:
        if not isinstance(self.stage, int) or self.stage < 1:
            raise ValueError("trigger stage must be a positive integer")

    def evaluate(self, *, invoked_stage: int) -> bool:
        """Whether the currently invoked stage satisfies this trigger."""
        if self.match is StageMatch.EXACT:
            return self.stage == invoked_stage
        # AT_OR_ABOVE -- the corpus rule: lower-stage obligations continue at higher stages.
        return self.stage <= invoked_stage


@dataclass(frozen=True, slots=True)
class StandingOrderActionClause:
    """One explicit action in the order's action list.

    `parameters` is deliberately closed: it is a frozendict of string keys to values that are
    themselves strings, ints, bools, None or nested frozendicts. Anything that could carry code
    or an arbitrary instruction is refused by the schema and by the model's own __post_init__.
    """

    action: StandingOrderAction
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", self._freeze(self.parameters))

    @staticmethod
    def _freeze(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return frozendict({k: StandingOrderActionClause._freeze(v) for k, v in value.items()})
        if isinstance(value, (list, tuple)):
            return tuple(StandingOrderActionClause._freeze(v) for v in value)
        raise ValueError(f"action parameters may not contain {type(value)!r}")


class frozendict(dict[str, Any]):
    """A hashable, frozen dictionary.

    Built on dict so it is a drop-in replacement in comparisons and serialisation, but hashable
    so it can live in sets and as dict keys. Construction accepts the same kwargs as dict.
    """

    def __init__(self, mapping=(), **kwargs: Any) -> None:
        super().__init__(mapping, **kwargs)

    def __hash__(self) -> int:
        return hash(tuple(sorted((k, _freeze_value(v)) for k, v in self.items())))

    def __repr__(self) -> str:
        return f"frozendict({dict.__repr__(self)})"


def _freeze_value(value: Any) -> Any:
    """Recursively freeze a value into hashable equivalents."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict) and not isinstance(value, frozendict):
        return frozendict({k: _freeze_value(v) for k, v in value.items()})
    if isinstance(value, frozendict):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(v) for v in value)
    raise ValueError(f"action parameters may not contain {type(value)!r}")


@dataclass(frozen=True, slots=True)
class StandingOrder:
    """A signed, time-bounded pre-commitment from one supervisor for one site.

    The schema field list you asked for is the public surface. Everything below `signed_at` is
    lifecycle bookkeeping derived at signing or at trigger time -- never user-editable.
    """

    # --- the schema you specified ----------------------------------------------
    standing_order_id: StandingOrderId
    site_id: str
    supervisor_id: str
    trigger: StageInvocationTrigger
    actions: tuple[StandingOrderActionClause, ...]
    valid_from: datetime
    valid_until: datetime
    status: StandingOrderStatus
    created_at: datetime
    signed_at: datetime | None = None

    # --- derived bookkeeping (set by lifecycle transitions, never by a user) ----
    commitment_hash: str | None = None
    trigger_fingerprint: str | None = None
    triggered_at: datetime | None = None
    completed_at: datetime | None = None
    expired_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.site_id, str) or not self.site_id.strip():
            raise ValueError("site_id must be a non-empty string")
        if not isinstance(self.supervisor_id, str) or not self.supervisor_id.strip():
            raise ValueError("supervisor_id must be a non-empty string")
        if (
            self.standing_order_id is None
            or not isinstance(self.standing_order_id, str)
            or not self.standing_order_id.strip()
        ):
            raise ValueError("standing_order_id must be a non-empty string")
        if not self.actions:
            raise ValueError("a standing order must pre-commit to at least one action")
        if not isinstance(self.valid_from, datetime) or self.valid_from.utcoffset() is None:
            raise ValueError("valid_from must be a timezone-aware instant")
        if not isinstance(self.valid_until, datetime) or self.valid_until.utcoffset() is None:
            raise ValueError("valid_until must be a timezone-aware instant")
        if self.valid_from >= self.valid_until:
            raise ValueError("valid_from must precede valid_until")
        if (
            self.created_at is None
            or not isinstance(self.created_at, datetime)
            or self.created_at.utcoffset() is None
        ):
            raise ValueError("created_at must be a timezone-aware instant")
        if self.signed_at is not None and (
            not isinstance(self.signed_at, datetime) or self.signed_at.utcoffset() is None
        ):
            raise ValueError("signed_at, when present, must be a timezone-aware instant")

    @property
    def has_signed(self) -> bool:
        return self.signed_at is not None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            StandingOrderStatus.COMPLETED,
            StandingOrderStatus.EXPIRED,
        )

    def commitment_payload(self) -> dict:
        """The fields over which commitment_hash is computed, in a stable order."""
        return {
            "standing_order_id": self.standing_order_id,
            "site_id": self.site_id,
            "supervisor_id": self.supervisor_id,
            "trigger": {
                "stage": self.trigger.stage,
                "match": self.trigger.match.value,
                "type": self.trigger.type.value,
            },
            "actions": [
                {
                    "action": clause.action.value,
                    "parameters": dict(clause.parameters),
                }
                for clause in self.actions
            ],
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

    def compute_commitment_hash(self) -> str:
        """SHA-256 over the signed fields, same shape as Parchi.content_hash."""
        canonical = str(self.commitment_payload())
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def with_commitment_hash(self) -> StandingOrder:
        """Return a new order with commitment_hash set over the current signed fields."""
        assert self.has_signed, "commitment_hash is only meaningful once signed"
        if self.commitment_hash is not None:
            return self
        # Build kwargs preserving the original actions tuple (asdict would convert
        # StandingOrderActionClause instances into plain dicts, which commitment_payload
        # does not accept).
        kwargs: dict[str, Any] = {
            "standing_order_id": self.standing_order_id,
            "site_id": self.site_id,
            "supervisor_id": self.supervisor_id,
            "trigger": self.trigger,
            "actions": self.actions,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "status": self.status,
            "created_at": self.created_at,
            "signed_at": self.signed_at,
            "commitment_hash": self.compute_commitment_hash(),
            "trigger_fingerprint": self.trigger_fingerprint,
            "triggered_at": self.triggered_at,
            "completed_at": self.completed_at,
            "expired_at": self.expired_at,
        }
        return StandingOrder(**kwargs)

    def compute_trigger_fingerprint(self, *, order_doc_id: str, order_sha256: str) -> str:
        """Fingerprint for a specific invocation event, derived from this order."""
        return trigger_fingerprint(
            standing_order_id=self.standing_order_id,
            site_id=self.site_id,
            stage=self.trigger.stage,
            order_doc_id=order_doc_id,
            order_sha256=order_sha256,
        )


@dataclass(frozen=True, slots=True)
class TriggerRun:
    """One run of the standing-order machine, keyed on its trigger fingerprint.

    The fingerprint and the surviving parchi ids are the idempotency contract: a redelivery of
    the same trigger re-derives the same run and the same parchi ids.
    """

    fingerprint: str
    standing_order_id: str
    site_id: str
    stage: int
    order_doc_id: str
    order_sha256: str
    started_at: datetime
    status: StandingOrderStatus
    parchi_ids: tuple[str, ...] = ()
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.fingerprint, str) or not self.fingerprint.strip():
            raise ValueError("fingerprint must be a non-empty string")
        if not self.parchi_ids:
            raise ValueError("a trigger run must carry at least the parchi ids it created")
        if (
            self.started_at is None
            or not isinstance(self.started_at, datetime)
            or self.started_at.utcoffset() is None
        ):
            raise ValueError("started_at must be a timezone-aware instant")
