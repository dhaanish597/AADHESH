"""Parchi (पर्ची) -- the slip a displaced worker ends up holding, and its lifecycle.

```
DRAFT --issue--> PENDING_ACK --acknowledge--> ACKNOWLEDGED --seal--> SEALED  (terminal)
  |                   |                             |
  +------void---------+------------void-------------+--> VOID                (terminal)
```

Three rules are load-bearing and all three are enforced here as well as at the authorization
boundary:

  * **Only the worker named on the parchi may acknowledge it.** A halt record is incomplete
    until the people it displaced have confirmed it themselves. Cedar denies proxy
    acknowledgement at the boundary; this module refuses it again, because a rule checked in
    exactly one place is one refactor away from not existing.
  * **Acknowledging and sealing are different acts.** ACKNOWLEDGED is the worker's
    confirmation; SEALED is the system freezing the record over a content hash. Keeping them
    apart is what makes "confirmed at T1" and "frozen at T2" separately provable.
  * **SEALED is terminal.** Sealing computes a content hash over the evidentiary fields.
    Evidence that can be edited afterwards is not evidence. There is deliberately no `edit`,
    `update` or `amend` here: a correction is a new event, never a mutation of the record.

Every transition returns a NEW parchi. Nothing here mutates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from aadesh_core.domain import (
    AcknowledgementMethod,
    InvokedStage,
    ParchiState,
    Provenance,
    StationReading,
)
from aadesh_core.errors import IllegalParchiTransition

PARCHI_SCHEMA_VERSION = "parchi/2"
"""Bumped from the acknowledged/sealed split. Sealed records state the version they were
frozen under, so a later reader can tell which shape of evidence they are holding."""


@dataclass(frozen=True, slots=True)
class Parchi:
    """An immutable record that one named worker was displaced by one invoked GRAP stage."""

    parchi_id: str
    site_id: str
    worker_id: str
    state: ParchiState
    created_at: datetime

    stage: InvokedStage | None
    order_sha256: str | None
    reading: StationReading | None

    obligation_ids: tuple[str, ...]
    entitlement_refs: tuple[str, ...]
    readiness_checklist: tuple[str, ...]
    displaced_worker_days: int

    issued_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    sealed_at: datetime | None = None
    content_hash: str | None = None
    shared_for_assistance: bool = False
    void_reason: str | None = None

    # --- Prompt 5: the workflow, acknowledgement and idempotency provenance -----
    workflow_execution_id: str | None = None
    """The standing-order / workflow execution that opened this parchi. None for a parchi
    opened by hand, which is honest rather than a guessed id."""

    source_event_id: str | None = None
    """The event that caused it. Carried through unchanged, never recomputed."""

    acknowledgement_method: AcknowledgementMethod | None = None
    """Set only by the worker's own explicit confirm. Opening or scanning is not a method."""

    acknowledgement_token_ref: str | None = None
    """A HASH-derived handle for the acknowledgement token, for audit correlation. The raw
    token is deliberately not representable on this record."""

    acknowledgement_event_id: str | None = None
    """The id of the ParchiAcknowledged event, so a replay can return the ORIGINAL event
    rather than minting a second one."""

    idempotency_key: str | None = None
    """The key creation was deduplicated on. Preserved so a caller can prove which key
    produced this parchi."""

    schema_version: str = PARCHI_SCHEMA_VERSION

    @property
    def provenance(self) -> Provenance | None:
        """Mirrors the reading. There is no independent setter, so it cannot be relabelled."""
        return self.reading.provenance if self.reading is not None else None

    @property
    def cites_measured_data(self) -> bool:
        """False for synthetic placeholders and for replayed readings.

        A parchi that is not backed by a live measurement must say so wherever it is shown.
        """
        return self.provenance is Provenance.MEASURED

    @property
    def is_terminal(self) -> bool:
        return self.state in (ParchiState.SEALED, ParchiState.VOID)

    @property
    def source_document_ids(self) -> tuple[str, ...]:
        """The documents this record rests on, derived rather than stored.

        Derived on purpose: a second stored copy could drift from the stage it came from,
        and then the evidence would list a source it does not actually cite.
        """
        if self.stage is None:
            return ()
        return (self.stage.order_doc_id,)

    @property
    def source_hashes(self) -> tuple[str, ...]:
        """The hashes proving those documents are the bytes relied on. Derived, for the same
        reason as `source_document_ids`."""
        return (self.order_sha256,) if self.order_sha256 else ()


def _require_state(parchi: Parchi, expected: ParchiState, action: str) -> None:
    if parchi.state is not expected:
        raise IllegalParchiTransition(
            f"Cannot {action} parchi {parchi.parchi_id}: it is {parchi.state.value}, "
            f"and {action} requires {expected.value}."
        )


def _evidentiary_payload(parchi: Parchi) -> dict:
    """The fields the content hash covers.

    Deliberately excludes `shared_for_assistance`: a worker later opting in to help must not
    invalidate the hash of a record that is already sealed.

    Deliberately INCLUDES every acknowledgement field and the workflow/idempotency
    provenance, because those are the claims the record is evidence FOR. A hash that did not
    cover them would let someone freeze a record and then assert a different acknowledging
    worker or a different originating execution.
    """
    return {
        "parchi_id": parchi.parchi_id,
        "site_id": parchi.site_id,
        "worker_id": parchi.worker_id,
        "schema_version": parchi.schema_version,
        "workflow_execution_id": parchi.workflow_execution_id,
        "source_event_id": parchi.source_event_id,
        "idempotency_key": parchi.idempotency_key,
        "stage": None if parchi.stage is None else parchi.stage.stage,
        "order_doc_id": None if parchi.stage is None else parchi.stage.order_doc_id,
        "order_sha256": parchi.order_sha256,
        "obligation_ids": list(parchi.obligation_ids),
        "entitlement_refs": list(parchi.entitlement_refs),
        "readiness_checklist": list(parchi.readiness_checklist),
        "displaced_worker_days": parchi.displaced_worker_days,
        "created_at": parchi.created_at.isoformat(),
        "acknowledged_at": None
        if parchi.acknowledged_at is None
        else parchi.acknowledged_at.isoformat(),
        "acknowledged_by": parchi.acknowledged_by,
        "acknowledgement_method": None
        if parchi.acknowledgement_method is None
        else parchi.acknowledgement_method.value,
        "acknowledgement_token_ref": parchi.acknowledgement_token_ref,
        "acknowledgement_event_id": parchi.acknowledgement_event_id,
        "reading": None
        if parchi.reading is None
        else {
            "station_id": parchi.reading.station_id,
            "parameter": parchi.reading.parameter,
            "value": parchi.reading.value,
            "observed_at": parchi.reading.observed_at.isoformat(),
            "provenance": parchi.reading.provenance.value,
        },
    }


def compute_content_hash(parchi: Parchi) -> str:
    """SHA-256 over a canonical serialisation of the evidentiary fields."""
    canonical = json.dumps(
        _evidentiary_payload(parchi), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def open_parchi(
    *,
    parchi_id: str,
    site_id: str,
    worker_id: str,
    stage: InvokedStage | None,
    reading: StationReading | None,
    obligation_ids: Sequence[str],
    entitlement_refs: Sequence[str],
    readiness_checklist: Sequence[str],
    displaced_worker_days: int,
    now: datetime,
    workflow_execution_id: str | None = None,
    source_event_id: str | None = None,
    idempotency_key: str | None = None,
) -> Parchi:
    """Create a DRAFT parchi.

    Note there is no `provenance` parameter. It is derived from `reading`, so a synthetic
    placeholder cannot be relabelled as a measurement by a caller.
    """
    return Parchi(
        parchi_id=parchi_id,
        site_id=site_id,
        worker_id=worker_id,
        state=ParchiState.DRAFT,
        created_at=now,
        stage=stage,
        order_sha256=None if stage is None else stage.order_sha256,
        reading=reading,
        obligation_ids=tuple(obligation_ids),
        entitlement_refs=tuple(entitlement_refs),
        readiness_checklist=tuple(readiness_checklist),
        displaced_worker_days=displaced_worker_days,
        workflow_execution_id=workflow_execution_id,
        source_event_id=source_event_id,
        idempotency_key=idempotency_key,
    )


def issue(parchi: Parchi, *, now: datetime) -> Parchi:
    """DRAFT -> PENDING_ACK. The parchi is now waiting on its worker."""
    _require_state(parchi, ParchiState.DRAFT, "issue")
    return replace(parchi, state=ParchiState.PENDING_ACK, issued_at=now)


def acknowledge(
    parchi: Parchi,
    *,
    actor_worker_id: str,
    now: datetime,
    method: AcknowledgementMethod = AcknowledgementMethod.QR_CONFIRMED,
    token_ref: str | None = None,
    event_id: str | None = None,
) -> Parchi:
    """PENDING_ACK -> ACKNOWLEDGED, and only at the hand of the worker named on the parchi.

    This records the confirmation. It does not seal; `seal` does that, and only once this
    has happened. `token_ref` must be the hash-derived handle, never a raw token -- the
    caller is responsible for that, and `aadesh_core.parchi_ack.tokens` never hands out a
    raw token for anything but display.
    """
    _require_state(parchi, ParchiState.PENDING_ACK, "acknowledge")

    if actor_worker_id != parchi.worker_id:
        raise IllegalParchiTransition(
            f"Cannot acknowledge parchi {parchi.parchi_id}: only the worker named on it "
            f"({parchi.worker_id}) may acknowledge it, not {actor_worker_id}. "
            f"A halt record is incomplete until the worker confirms it themselves."
        )

    return replace(
        parchi,
        state=ParchiState.ACKNOWLEDGED,
        acknowledged_at=now,
        acknowledged_by=actor_worker_id,
        acknowledgement_method=method,
        acknowledgement_token_ref=token_ref,
        acknowledgement_event_id=event_id,
    )


def seal(parchi: Parchi, *, now: datetime) -> Parchi:
    """ACKNOWLEDGED -> SEALED. Freezes the record over a content hash.

    Sealing is deliberately NOT reachable from PENDING_ACK. If it were, a supervisor could
    produce a sealed parchi that no worker ever confirmed, which is precisely the thing the
    parchi exists to make impossible.
    """
    _require_state(parchi, ParchiState.ACKNOWLEDGED, "seal")
    sealed = replace(parchi, state=ParchiState.SEALED, sealed_at=now)
    return replace(sealed, content_hash=compute_content_hash(sealed))


def void(parchi: Parchi, *, reason: str, now: datetime) -> Parchi:
    """Cancel a parchi that has not been sealed."""
    if parchi.is_terminal:
        raise IllegalParchiTransition(
            f"Cannot void parchi {parchi.parchi_id}: it is {parchi.state.value}, which is terminal."
        )
    return replace(parchi, state=ParchiState.VOID, void_reason=reason, sealed_at=now)


def share_for_assistance(parchi: Parchi, *, shared: bool = True) -> Parchi:
    """Record that the worker opted in to facilitator assistance.

    Opting in grants AssistClaim (a redacted view) and nothing more -- Cedar's
    `assist-is-not-disclosure` rule still forbids ViewParchi. Excluded from the content hash
    so this never invalidates an already-sealed record.
    """
    return replace(parchi, shared_for_assistance=shared)
