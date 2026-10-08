"""Parchi creation: the interface a compliance workflow calls, and its idempotency contract.

INTEGRATION CONTRACT (for Prompt 4's standing-order / Step Functions machine)
=============================================================================

Prompt 4 is built separately, so this module deliberately does not import it, guess at its
types, or wrap its unfinished code. Instead it publishes the smallest interface that machine
needs, in domain terms that will not move when Prompt 4 lands:

    execution  -- a `WorkflowExecution`: which run of which workflow, on which site, set off
                  by which event. Prompt 4 supplies its state-machine execution id here.
    worker     -- a `RosterEntry`: who was displaced.
    provenance -- a `ParchiProvenance`: the cited stage, the reading, the obligation and
                  entitlement REFERENCES, and the displaced-worker days.
    key        -- an idempotency key. **Prompt 4 must derive this deterministically from its
                  own execution identity**, e.g. `f"{execution_id}:{worker_id}"`, and pass the
                  same value on every retry of the same step. That is what makes a Step
                  Functions retry safe: a re-invocation returns the parchi the first call
                  created instead of minting a second one.

The two entry points:

    create_parchi_for_worker(...)   -> ParchiIssue       one worker, one parchi
    create_parchis_for_roster(...)  -> tuple[ParchiIssue, ...]   the active roster

Both are deterministic and idempotent on the key. Neither touches the network, a model or a
clock it was not handed.

THREE THINGS THIS DOES NOT DO, ON PURPOSE
-----------------------------------------
1. **It does not decide entitlement.** `entitlement_refs` are references to CITED clauses and
   are copied through untouched. No amount is computed, and `displaced_worker_days` is the
   caller's number, not worker_count x days.
2. **It does not issue CAQM invocations.** It records the stage it is GIVEN. If the corpus has
   no active invocation, the caller passes a replay or synthetic stage and the parchi's
   provenance says so.
3. **It does not authorize.** Authorization is Cedar's job at the API boundary (Prompt 6).
   This module is the domain; it enforces the identity rules it owns (only the named worker
   may acknowledge in `service.acknowledge_parchi`) and leaves role policy upstream.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from aadesh_core.domain import InvokedStage, ParchiState, StationReading
from aadesh_core.errors import DuplicateIdempotencyKey, IllegalParchiTransition
from aadesh_core.parchi import Parchi, issue, open_parchi
from aadesh_core.parchi_ack.roster import Roster, RosterEntry
from aadesh_core.parchi_ack.tokens import (
    DEFAULT_TOKEN_TTL,
    AcknowledgementQr,
    mint_acknowledgement_token,
)
from aadesh_core.ports.parchi_ack import AcknowledgementTokenStore, ParchiAckStore


@dataclass(frozen=True, slots=True)
class WorkflowExecution:
    """One run of one compliance workflow.

    `source_event_id` is the event that set the run off -- for Prompt 4, the official stage
    invocation that matched a standing order's trigger. It is carried onto every parchi the
    run opens, unchanged, so the record can be traced back to the event that caused it.
    """

    execution_id: str
    site_id: str
    source_event_id: str

    def __post_init__(self) -> None:
        for name in ("execution_id", "site_id", "source_event_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"WorkflowExecution requires a non-empty {name}")

    def idempotency_key_for(self, worker_id: str) -> str:
        """The key a worker's parchi is created under, derived rather than invented.

        Deterministic on purpose: a Step Functions retry recomputes the same key and therefore
        finds the parchi the first attempt created.
        """
        return f"{self.execution_id}:{worker_id}"

    def parchi_id_for(self, worker_id: str) -> str:
        return f"parchi:{self.execution_id}:{worker_id}"


@dataclass(frozen=True, slots=True)
class ParchiProvenance:
    """Everything the parchi rests on. Copied onto the record, never recomputed.

    `reading` carries the provenance label (measured / synthetic / replay) and the parchi
    derives its own from it, so a synthetic placeholder cannot be relabelled in transit.

    `entitlement_refs` are REFERENCES. Nothing here can hold an amount.
    """

    stage: InvokedStage | None
    reading: StationReading | None
    obligation_ids: tuple[str, ...] = ()
    entitlement_refs: tuple[str, ...] = ()
    readiness_checklist: tuple[str, ...] = ()
    displaced_worker_days: int = 1

    def __post_init__(self) -> None:
        if self.displaced_worker_days < 0:
            raise ValueError("displaced_worker_days cannot be negative")


@dataclass(frozen=True, slots=True)
class ParchiIssue:
    """The result of creating one parchi.

    `qr` is None when `replayed` is True, and that is not an oversight. The raw token is
    stored nowhere, so a replay cannot re-issue the same link; minting a different one would
    leave two live links for one parchi. `issue_acknowledgement_qr` is the explicit act that
    mints a replacement.
    """

    parchi: Parchi
    qr: AcknowledgementQr | None
    replayed: bool


def _open_one(
    *,
    parchi_id: str,
    execution: WorkflowExecution,
    worker: RosterEntry,
    provenance: ParchiProvenance,
    idempotency_key: str,
    now: datetime,
    store: ParchiAckStore,
    tokens: AcknowledgementTokenStore,
    ttl: timedelta,
) -> ParchiIssue:
    existing = store.find_by_idempotency_key(idempotency_key)
    if existing is not None:
        return ParchiIssue(parchi=existing, qr=None, replayed=True)

    parchi = issue(
        open_parchi(
            parchi_id=parchi_id,
            site_id=execution.site_id,
            worker_id=worker.worker_id,
            stage=provenance.stage,
            reading=provenance.reading,
            obligation_ids=provenance.obligation_ids,
            entitlement_refs=provenance.entitlement_refs,
            readiness_checklist=provenance.readiness_checklist,
            displaced_worker_days=provenance.displaced_worker_days,
            now=now,
            workflow_execution_id=execution.execution_id,
            source_event_id=execution.source_event_id,
            idempotency_key=idempotency_key,
        ),
        now=now,
    )

    try:
        store.save_new(parchi)
    except DuplicateIdempotencyKey:
        # The lookup above missed because the competing caller had not finished writing yet.
        # Their record is the one that exists; ours was never written. Return theirs, and
        # mint nothing -- a second live link for one parchi would be a second thing a worker
        # could confirm.
        winner = store.find_by_idempotency_key(idempotency_key)
        if winner is None:  # pragma: no cover -- a store that refuses the write must have one
            raise
        return ParchiIssue(parchi=winner, qr=None, replayed=True)

    qr, token = mint_acknowledgement_token(
        parchi_id=parchi.parchi_id,
        worker_id=worker.worker_id,
        now=now,
        ttl=ttl,
    )
    tokens.put(token)
    return ParchiIssue(parchi=parchi, qr=qr, replayed=False)


def create_parchi_for_worker(
    *,
    parchi_id: str | None = None,
    execution: WorkflowExecution,
    worker: RosterEntry,
    provenance: ParchiProvenance,
    idempotency_key: str,
    now: datetime,
    store: ParchiAckStore,
    tokens: AcknowledgementTokenStore,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
) -> ParchiIssue:
    """Open one PENDING_ACK parchi for one worker, at most once per idempotency key."""
    if not idempotency_key.strip():
        raise ValueError(
            "create_parchi_for_worker requires an idempotency key. Without one there is no "
            "way to tell a retry from a genuine second displacement, and a retried workflow "
            "step would mint a duplicate parchi."
        )
    return _open_one(
        parchi_id=parchi_id or execution.parchi_id_for(worker.worker_id),
        execution=execution,
        worker=worker,
        provenance=provenance,
        idempotency_key=idempotency_key,
        now=now,
        store=store,
        tokens=tokens,
        ttl=ttl,
    )


def create_parchis_for_roster(
    *,
    execution: WorkflowExecution,
    roster: Roster,
    provenance: ParchiProvenance,
    idempotency_key: str,
    now: datetime,
    store: ParchiAckStore,
    tokens: AcknowledgementTokenStore,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
    parchi_id_for: Callable[[str], str] | None = None,
) -> tuple[ParchiIssue, ...]:
    """Open one parchi per ACTIVE roster entry, at most once per (key, worker).

    Per-worker keys are derived as `f"{idempotency_key}:{worker_id}"`, so a retry that happens
    to see a changed roster still cannot duplicate an existing parchi: the workers who were
    already handled resolve to their existing records, and only genuinely new ones are opened.

    Note what is NOT scaled by the roster size: `displaced_worker_days` and every
    `entitlement_refs` entry are passed through exactly as given. Worker count is a count of
    people, not a multiplier on a claim.
    """
    if roster.site_id != execution.site_id:
        raise ValueError(
            f"Roster is for site {roster.site_id!r} but execution {execution.execution_id!r} "
            f"is for site {execution.site_id!r}. Opening parches across sites would attach a "
            f"halt to the wrong roster."
        )

    choose_id = parchi_id_for or execution.parchi_id_for
    return tuple(
        _open_one(
            parchi_id=choose_id(entry.worker_id),
            execution=execution,
            worker=entry,
            provenance=provenance,
            idempotency_key=f"{idempotency_key}:{entry.worker_id}",
            now=now,
            store=store,
            tokens=tokens,
            ttl=ttl,
        )
        for entry in roster.active_entries()
    )


def issue_acknowledgement_qr(
    *,
    parchi: Parchi,
    now: datetime,
    tokens: AcknowledgementTokenStore,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
) -> AcknowledgementQr:
    """Mint a fresh acknowledgement link for a parchi that is still waiting on its worker.

    This is the "show me the QR again" operation, and it is the only way to get a link other
    than the one creation returns. It refuses anything that is not PENDING_ACK: a sealed
    record must not be reachable by a new link, and a draft has nobody to send it to yet.
    """
    if parchi.state is not ParchiState.PENDING_ACK:
        raise IllegalParchiTransition(
            f"Cannot issue an acknowledgement link for parchi {parchi.parchi_id}: it is "
            f"{parchi.state.value}. Only a parchi awaiting its worker's confirmation can be "
            f"linked to one."
        )

    qr, token = mint_acknowledgement_token(
        parchi_id=parchi.parchi_id,
        worker_id=parchi.worker_id,
        now=now,
        ttl=ttl,
    )
    tokens.put(token)
    return qr
