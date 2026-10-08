"""The acknowledgement service: the one place a worker's confirmation becomes a fact.

Everything security-relevant about acknowledgement is decided in this module, in one order:

  1. **Parse the payload.** A malformed string is refused before anything is looked up.
  2. **Resolve the token.** Unknown and expired are refused -- and refused identically to a
     forged one, so the error is not an oracle for guessing tokens.
  3. **Hand the parchi to `parchi.acknowledge`.** The domain refuses an actor who is not the
     worker named on the record, before any state changes.
  4. **Consume the token, compare-and-set.** If somebody else got there first, this raises and
     nothing is written. The loser loses here, not at the database.
  5. **Save, then record the audit event.** The saved record carries the event's id, so a
     replay can be recognised as a replay rather than an error.

Step 4 runs inside `IdempotencyLedger.execute_once`, keyed on the token hash. That is what
makes a double-tapped confirmation produce ONE acknowledgement event rather than two: the
second caller does not run the operation at all, it is handed the first caller's result. It
is deliberately not "try it and catch the duplicate" -- that still performs the work twice,
it just hides the evidence of having done so.

The event id is minted here and stored on the parchi. That is the join between the immutable
record and the append-only trail: given a sealed parchi you can name the audit line that
proves the worker confirmed it.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import datetime

from aadesh_core.domain import ParchiState, Provenance
from aadesh_core.errors import (
    IllegalParchiTransition,
    TokenRejected,
    TokenRejectionReason,
    WrongWorker,
)
from aadesh_core.parchi import Parchi, acknowledge, seal
from aadesh_core.parchi_ack.events import (
    ParchiAcknowledged,
    ParchiSealed,
)
from aadesh_core.parchi_ack.tokens import (
    AcknowledgementToken,
    hash_token,
    parse_acknowledgement_payload,
)
from aadesh_core.ports.audit import AuditLog
from aadesh_core.ports.parchi_ack import (
    AcknowledgementTokenStore,
    IdempotencyLedger,
    ParchiAckStore,
)


@dataclass(frozen=True, slots=True)
class AcknowledgementOutcome:
    """What a confirmation produced, and whether this call was the one that produced it."""

    parchi: Parchi
    event: ParchiAcknowledged
    already_confirmed: bool
    """True when this token had been used before and the caller was handed the ORIGINAL
    acknowledgement rather than a second one. A retried request is not an error; it is the
    same fact, reported twice."""


@dataclass(frozen=True, slots=True)
class PendingParchiView:
    """What the worker is shown BEFORE they confirm.

    Readable by whoever holds the link, which is the point: the link is the worker's own
    credential. It therefore contains no contact detail, no identity document and no figure
    -- there is nothing here that would be a problem on a screen someone else can see.
    """

    parchi_id: str
    site_id: str
    worker_id: str
    state: ParchiState
    created_at: datetime
    stage: int | None
    """The GRAP stage number as invoked by CAQM. An int, not a computed AQI band."""
    provenance: Provenance | None
    cites_measured_data: bool
    obligation_ids: tuple[str, ...]
    entitlement_refs: tuple[str, ...]
    readiness_checklist: tuple[str, ...]
    displaced_worker_days: int
    source_document_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    expires_at: datetime


def _new_event_id() -> str:
    """A fresh, opaque event id. Not derived from the token: an id built out of the credential
    would let anyone holding one link compute the identifiers of the audit trail."""
    return f"evt-ack-{secrets.token_hex(8)}"


def _resolve_token(
    payload: str,
    *,
    now: datetime,
    tokens: AcknowledgementTokenStore,
    allow_consumed: bool = False,
) -> AcknowledgementToken:
    """Parse, look up and check expiry. Every failure is a `TokenRejected`, and the caller
    cannot tell which failure it was from the message."""
    raw = parse_acknowledgement_payload(payload)
    token = tokens.get(hash_token(raw))

    if token is None:
        raise TokenRejected(TokenRejectionReason.UNKNOWN)
    if token.is_expired(now):
        raise TokenRejected(TokenRejectionReason.EXPIRED)
    if not allow_consumed and token.state.value == "consumed":
        raise TokenRejected(TokenRejectionReason.CONSUMED)
    return token


def _parchi_for(token: AcknowledgementToken, store: ParchiAckStore) -> Parchi:
    """The parchi a token points at.

    A token whose parchi is missing, or whose parchi names a different worker than the token
    does, is reported as UNKNOWN rather than as an internal inconsistency: from the outside
    that is exactly what it is, an identifier this system cannot honour.
    """
    parchi = store.get(token.parchi_id)
    if parchi is None or parchi.worker_id != token.worker_id:
        raise TokenRejected(TokenRejectionReason.UNKNOWN)
    return parchi


def acknowledge_parchi(
    *,
    payload: str,
    actor_worker_id: str,
    now: datetime,
    store: ParchiAckStore,
    tokens: AcknowledgementTokenStore,
    ledger: IdempotencyLedger,
    audit: AuditLog,
    event_id: str | None = None,
) -> AcknowledgementOutcome:
    """Confirm a parchi at the hand of the worker named on it. At most once, ever.

    `actor_worker_id` is who the caller has authenticated as. The raw `payload` is the
    credential; the two must agree, and the parchi's own worker must agree with both.
    """
    # A used token still has to RESOLVE, so that a double-tap can be recognised as the same
    # confirmation rather than bounced as an error. What stops the second use is not this
    # lookup but the ledger (which memorises the outcome per token hash) and the
    # compare-and-set inside `confirm` -- both of which are below.
    token = _resolve_token(payload, now=now, tokens=tokens, allow_consumed=True)
    before = _parchi_for(token, store)

    # The identity check runs BEFORE the ledger, so it applies to replays too. If it ran only
    # inside the memoised operation, a second caller presenting somebody else's used link
    # would be handed the original acknowledgement instead of being refused -- the identity
    # rule would silently hold only for first-time callers.
    if actor_worker_id != before.worker_id:
        raise WrongWorker(before.parchi_id)

    # Read before the atomic section, purely to report `already_confirmed` honestly. It is
    # not what makes the operation safe -- the ledger and the compare-and-set are -- so a
    # stale read here can at worst mislabel a flag in a race, never duplicate a fact.
    already = before.state is not ParchiState.PENDING_ACK

    def confirm() -> AcknowledgementOutcome:
        resolved_event_id = event_id or _new_event_id()

        # Raises for a non-pending parchi. The identity rule was checked above, and is checked
        # AGAIN inside `acknowledge` -- a rule enforced in one place is one refactor away from
        # not existing.
        acknowledged = acknowledge(
            before,
            actor_worker_id=actor_worker_id,
            now=now,
            token_ref=token.reference,
            event_id=resolved_event_id,
        )

        # Compare-and-set. Raises if somebody already used this link; nothing is written.
        tokens.consume(token.token_hash, at=now, event_id=resolved_event_id)

        store.save(acknowledged)

        event = ParchiAcknowledged(
            event_id=resolved_event_id,
            parchi_id=acknowledged.parchi_id,
            worker_id=acknowledged.worker_id,
            occurred_at=now,
            acknowledgement_method=acknowledged.acknowledgement_method,
            token_reference=token.reference,
            workflow_execution_id=acknowledged.workflow_execution_id,
            site_id=acknowledged.site_id,
        )
        audit.record(event=event.event_type, detail=event.as_audit_detail())
        return AcknowledgementOutcome(parchi=acknowledged, event=event, already_confirmed=False)

    outcome = ledger.execute_once(key=f"ack:{token.token_hash}", compute=confirm)

    # Re-read so a replay reports the CURRENT state rather than the state at confirmation
    # time: a parchi confirmed and then sealed must not read as merely acknowledged.
    current = store.get(outcome.parchi.parchi_id) or outcome.parchi
    return replace(outcome, parchi=current, already_confirmed=already)


def resolve_parchi_for_payload(
    *,
    payload: str,
    now: datetime,
    store: ParchiAckStore,
    tokens: AcknowledgementTokenStore,
) -> Parchi:
    """The parchi a payload refers to, WITHOUT consuming the token or changing anything.

    This is the read the authorization boundary needs: to ask "may this principal
    acknowledge THIS parchi?" the caller must first know which parchi the link names. It
    deliberately differs from `describe_pending_parchi` in one respect -- a token that has
    already been used still resolves here. A replay must reach the authorization decision and
    then the domain's identity check, exactly as a first attempt does; refusing it earlier
    would mean a second caller presenting somebody else's used link got a token error instead
    of a permission error, which is a different fact told to the wrong person.

    Resolving is not using. Nothing is written, no state moves, and the token stays live.
    """
    token = _resolve_token(payload, now=now, tokens=tokens, allow_consumed=True)
    return _parchi_for(token, store)


def describe_pending_parchi(
    *,
    payload: str,
    now: datetime,
    store: ParchiAckStore,
    tokens: AcknowledgementTokenStore,
) -> PendingParchiView:
    """Show the worker what they are being asked to confirm. Does not confirm anything.

    A token that has already been used is refused here rather than answered: this function
    describes a parchi that is WAITING, and a used link is not waiting for anything. The
    worker who already confirmed reaches their record through `acknowledge_parchi`, which
    recognises the replay and returns the original confirmation.
    """
    token = _resolve_token(payload, now=now, tokens=tokens)
    parchi = _parchi_for(token, store)

    return PendingParchiView(
        parchi_id=parchi.parchi_id,
        site_id=parchi.site_id,
        worker_id=parchi.worker_id,
        state=parchi.state,
        created_at=parchi.created_at,
        stage=None if parchi.stage is None else parchi.stage.stage,
        provenance=parchi.provenance,
        cites_measured_data=parchi.cites_measured_data,
        obligation_ids=parchi.obligation_ids,
        entitlement_refs=parchi.entitlement_refs,
        readiness_checklist=parchi.readiness_checklist,
        displaced_worker_days=parchi.displaced_worker_days,
        source_document_ids=parchi.source_document_ids,
        source_hashes=parchi.source_hashes,
        expires_at=token.expires_at,
    )


def seal_parchi(
    *,
    parchi: Parchi,
    now: datetime,
    store: ParchiAckStore,
    audit: AuditLog,
    event_id: str | None = None,
) -> Parchi:
    """Freeze an acknowledged parchi over its content hash.

    Idempotent on an already-sealed record, on purpose: a workflow retry of the seal step must
    not fail, and re-sealing must not rewrite the moment the record was frozen. The original
    `sealed_at` and `content_hash` are returned untouched.

    Everything else is refused by the domain -- PENDING_ACK included, so a supervisor cannot
    produce a sealed parchi that no worker ever confirmed.
    """
    if parchi.state is ParchiState.SEALED:
        return parchi
    if parchi.state is ParchiState.VOID:
        raise IllegalParchiTransition(
            f"Cannot seal parchi {parchi.parchi_id}: it is void. A cancelled record is not "
            f"evidence of anything and must not be frozen as if it were."
        )

    sealed = seal(parchi, now=now)
    store.save(sealed)

    event = ParchiSealed(
        event_id=event_id or _new_event_id(),
        parchi_id=sealed.parchi_id,
        site_id=sealed.site_id,
        worker_id=sealed.worker_id,
        occurred_at=now,
        content_hash=sealed.content_hash or "",
    )
    audit.record(event=event.event_type, detail=event.as_audit_detail())
    return sealed
