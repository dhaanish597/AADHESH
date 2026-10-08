"""INVARIANT: a worker's own confirmation is the only thing that acknowledges a parchi,
it happens once, and it leaves a trace that is safe to keep forever.

This file is the acknowledgement path's security surface, so it is written adversarially.
Each test names a specific way someone could get an undeserved acknowledgement, or leak
something, and pins the answer:

  * a supervisor confirming on a worker's behalf                -> refused
  * another worker confirming with a forwarded screenshot       -> refused
  * a forged or truncated token                                 -> refused, indistinguishably
  * a link used yesterday                                       -> refused, indistinguishably
  * a link used twice, by anyone                                -> one acknowledgement, one event
  * the raw token ending up in the audit trail or the record    -> must not happen
  * "confirming" being treated as "sealing"                     -> must not happen

The uniform-rejection tests are the point of the `reason`/`message` split: a prober must not
be able to tell a forged token from an expired one from one already used.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.domain import AcknowledgementMethod, ParchiState, Provenance
from aadesh_core.errors import (
    IllegalParchiTransition,
    TokenRejected,
    TokenRejectionReason,
    WrongWorker,
)
from aadesh_core.parchi_ack import (
    ParchiAcknowledged,
    ParchiProvenance,
    RosterEntry,
    WorkflowExecution,
    create_parchi_for_worker,
    issue_acknowledgement_qr,
)
from aadesh_core.parchi_ack.events import EVENT_TYPE_PARCHI_ACKNOWLEDGED
from aadesh_core.parchi_ack.service import (
    AcknowledgementOutcome,
    acknowledge_parchi,
    describe_pending_parchi,
    seal_parchi,
)
from aadesh_core.parchi_ack.tokens import (
    TOKEN_SCHEME,
    hash_token,
    parse_acknowledgement_payload,
)
from tests.support.builders import FIXED_NOW, invoked_stage, reading

LATER = FIXED_NOW + timedelta(hours=2)
DAY_AFTER = FIXED_NOW + timedelta(days=2)

WORKER = "worker-001"
OTHER_WORKER = "worker-002"

EXECUTION = WorkflowExecution(
    execution_id="exec-2026-10-08-001",
    site_id="site-001",
    source_event_id="evt-stage-invocation-001",
)

PROVENANCE = ParchiProvenance(
    stage=invoked_stage(),
    reading=reading(provenance=Provenance.MEASURED),
    obligation_ids=("ob-dust-01",),
    entitlement_refs=("ent-cited-clause-01",),
    readiness_checklist=("Welfare board registration number",),
    displaced_worker_days=3,
)


class Harness:
    """One wired-up acknowledgement path, with handles on everything it touched."""

    def __init__(self) -> None:
        self.store = InMemoryParchiStore()
        self.tokens = InMemoryAcknowledgementTokenStore()
        self.ledger = InMemoryIdempotencyLedger()
        self.audit = RecordingAuditLog()

    def open_parchi(self, *, worker_id: str = WORKER, now=FIXED_NOW):
        issue = create_parchi_for_worker(
            parchi_id=f"parchi-{worker_id}",
            execution=EXECUTION,
            worker=RosterEntry(worker_id=worker_id, display_name="Worker A"),
            provenance=PROVENANCE,
            idempotency_key=f"idem-{worker_id}",
            now=now,
            store=self.store,
            tokens=self.tokens,
        )
        assert issue.qr is not None
        return issue

    def confirm(self, payload: str, *, actor: str = WORKER, now=FIXED_NOW):
        return acknowledge_parchi(
            payload=payload,
            actor_worker_id=actor,
            now=now,
            store=self.store,
            tokens=self.tokens,
            ledger=self.ledger,
            audit=self.audit,
        )


@pytest.fixture
def h() -> Harness:
    return Harness()


# --- the happy path ---------------------------------------------------------


def test_a_worker_confirming_with_their_own_link_acknowledges_the_parchi(h):
    issue = h.open_parchi()

    outcome = h.confirm(issue.qr.payload)

    assert isinstance(outcome, AcknowledgementOutcome)
    assert outcome.parchi.state is ParchiState.ACKNOWLEDGED
    assert h.store.get(issue.parchi.parchi_id).state is ParchiState.ACKNOWLEDGED


def test_confirming_records_who_confirmed_and_when(h):
    issue = h.open_parchi()

    outcome = h.confirm(issue.qr.payload, now=LATER)

    assert outcome.parchi.acknowledged_at == LATER
    assert outcome.parchi.acknowledged_by == WORKER
    assert outcome.parchi.acknowledgement_method is AcknowledgementMethod.QR_CONFIRMED


def test_confirming_produces_the_event_that_proves_it(h):
    issue = h.open_parchi()

    outcome = h.confirm(issue.qr.payload)

    assert isinstance(outcome.event, ParchiAcknowledged)
    assert outcome.event.parchi_id == issue.parchi.parchi_id
    assert outcome.event.worker_id == WORKER
    assert outcome.event.occurred_at == FIXED_NOW
    assert outcome.event.acknowledgement_method is AcknowledgementMethod.QR_CONFIRMED
    assert outcome.parchi.acknowledgement_event_id == outcome.event.event_id
    assert outcome.event.event_id in h.audit.all_text()


def test_the_parchi_records_a_token_reference_and_never_the_token(h):
    issue = h.open_parchi()
    raw = issue.qr.payload

    outcome = h.confirm(raw)

    ref = outcome.parchi.acknowledgement_token_ref
    assert ref is not None and ref.startswith("tok_")
    assert ref not in raw
    assert raw not in repr(outcome.parchi)


def test_confirming_is_not_sealing(h):
    """The two acts stay separate: the worker confirms, the system freezes."""
    issue = h.open_parchi()

    outcome = h.confirm(issue.qr.payload)

    assert outcome.parchi.state is ParchiState.ACKNOWLEDGED
    assert outcome.parchi.state is not ParchiState.SEALED
    assert outcome.parchi.sealed_at is None
    assert outcome.parchi.content_hash is None


def test_confirming_does_not_invent_an_entitlement(h):
    issue = h.open_parchi()
    outcome = h.confirm(issue.qr.payload)

    for field in ("amount_inr", "entitlement_amount", "compensation", "rupees"):
        assert not hasattr(outcome.parchi, field)
    assert outcome.parchi.entitlement_refs == ("ent-cited-clause-01",)


# --- only the named worker may confirm --------------------------------------


def test_the_named_worker_is_the_only_one_who_can_confirm(h):
    """A supervisor holding the slip cannot confirm it, and neither can a colleague."""
    issue = h.open_parchi()

    with pytest.raises(WrongWorker):
        h.confirm(issue.qr.payload, actor=OTHER_WORKER)

    assert h.store.get(issue.parchi.parchi_id).state is ParchiState.PENDING_ACK, (
        "a refused confirmation must not move the record"
    )
    assert h.audit.for_event(EVENT_TYPE_PARCHI_ACKNOWLEDGED) == ()


def test_somebody_else_cannot_hijack_a_used_link(h):
    """The identity rule is not a first-caller-only rule.

    Found by the demo CLI: if the identity check lived only inside the memoised operation, a
    colleague presenting an already-used link would be handed the original confirmation
    instead of being refused, because the ledger would answer without running it.
    """
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)

    with pytest.raises(WrongWorker):
        h.confirm(issue.qr.payload, actor=OTHER_WORKER)


def test_a_refused_confirmation_does_not_burn_the_workers_link(h):
    """A colleague's failed attempt must not leave the real worker unable to confirm."""
    issue = h.open_parchi()

    with pytest.raises(WrongWorker):
        h.confirm(issue.qr.payload, actor=OTHER_WORKER)

    assert h.confirm(issue.qr.payload).parchi.state is ParchiState.ACKNOWLEDGED


# --- rejections are uniform -------------------------------------------------


def test_a_malformed_payload_is_refused(h):
    h.open_parchi()
    with pytest.raises(TokenRejected) as exc:
        h.confirm("https://example.com/not-ours")
    assert exc.value.reason is TokenRejectionReason.MALFORMED


def test_an_unknown_but_well_formed_token_is_refused(h):
    h.open_parchi()
    forged = f"{TOKEN_SCHEME}{'A' * 43}"

    with pytest.raises(TokenRejected) as exc:
        h.confirm(forged)

    assert exc.value.reason in (TokenRejectionReason.UNKNOWN, TokenRejectionReason.MALFORMED)


def test_an_expired_link_is_refused(h):
    """The second day is too late, even for the right worker holding the right link."""
    issue = h.open_parchi()

    with pytest.raises(TokenRejected) as exc:
        h.confirm(issue.qr.payload, now=DAY_AFTER)

    assert exc.value.reason is TokenRejectionReason.EXPIRED
    assert h.store.get(issue.parchi.parchi_id).state is ParchiState.PENDING_ACK


@pytest.mark.parametrize(
    "reason",
    [
        TokenRejectionReason.MALFORMED,
        TokenRejectionReason.UNKNOWN,
        TokenRejectionReason.EXPIRED,
        TokenRejectionReason.CONSUMED,
    ],
)
def test_every_rejection_shows_the_caller_the_same_sentence(reason):
    """Otherwise the error message is an oracle for guessing tokens."""
    messages = {r: TokenRejected(r).message for r in TokenRejectionReason}
    assert len(set(messages.values())) == 1
    assert messages[reason] == messages[TokenRejectionReason.UNKNOWN]


def test_the_rejection_sentence_does_not_confirm_whether_a_token_exists(h):
    issue = h.open_parchi()
    real_expired = issue.qr.payload

    with pytest.raises(TokenRejected) as expired:
        h.confirm(real_expired, now=DAY_AFTER)
    with pytest.raises(TokenRejected) as forged:
        h.confirm(f"{TOKEN_SCHEME}{'B' * 43}")

    assert expired.value.message == forged.value.message


# --- a token is single-use --------------------------------------------------


def test_an_expired_link_really_is_expired_at_its_expiry_instant(h):
    issue = h.open_parchi()
    with pytest.raises(TokenRejected) as exc:
        h.confirm(issue.qr.payload, now=issue.qr.expires_at)
    assert exc.value.reason is TokenRejectionReason.EXPIRED


def test_a_token_that_was_used_cannot_be_used_again(h):
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)

    stored = h.tokens.get(issue.qr.token_hash)
    assert stored.state.value == "consumed"
    assert stored.consumed_event_id is not None

    with pytest.raises(TokenRejected) as exc:
        h.tokens.consume(issue.qr.token_hash, at=LATER, event_id="evt-other")
    assert exc.value.reason is TokenRejectionReason.CONSUMED


def test_consuming_an_unknown_token_is_refused(h):
    with pytest.raises(TokenRejected) as exc:
        h.tokens.consume("0" * 64, at=FIXED_NOW, event_id="evt-1")
    assert exc.value.reason is TokenRejectionReason.UNKNOWN


def test_an_expired_token_cannot_be_consumed(h):
    issue = h.open_parchi()
    with pytest.raises(TokenRejected) as exc:
        h.tokens.consume(issue.qr.token_hash, at=DAY_AFTER, event_id="evt-1")
    assert exc.value.reason is TokenRejectionReason.EXPIRED
    assert h.tokens.get(issue.qr.token_hash).state.value == "active", (
        "a refused consumption must not mark the token used"
    )


# --- replaying the same confirmation ----------------------------------------


def test_replaying_the_same_confirmation_writes_one_audit_event(h):
    """Double-tap on a flaky connection is one legal fact, not two."""
    issue = h.open_parchi()

    first = h.confirm(issue.qr.payload)
    second = h.confirm(issue.qr.payload)

    assert len(h.audit.for_event(EVENT_TYPE_PARCHI_ACKNOWLEDGED)) == 1
    assert first.event.event_id == second.event.event_id


def test_replaying_the_same_confirmation_reports_it_was_already_done(h):
    issue = h.open_parchi()

    first = h.confirm(issue.qr.payload)
    second = h.confirm(issue.qr.payload)

    assert first.already_confirmed is False
    assert second.already_confirmed is True
    assert second.event.event_id == first.event.event_id


def test_a_replay_does_not_move_the_acknowledgement_time(h):
    issue = h.open_parchi()

    first = h.confirm(issue.qr.payload, now=FIXED_NOW)
    second = h.confirm(issue.qr.payload, now=LATER)

    assert second.parchi.acknowledged_at == first.parchi.acknowledged_at == FIXED_NOW


def test_a_replay_returns_the_current_state_not_a_stale_copy(h):
    """Confirmation, then sealing, then a replay: the replay must show the sealed record."""
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)
    seal_parchi(parchi=h.store.get(issue.parchi.parchi_id), now=LATER, store=h.store, audit=h.audit)

    replay = h.confirm(issue.qr.payload)

    assert replay.parchi.state is ParchiState.SEALED
    assert replay.already_confirmed is True


def test_a_reissued_link_confirms_the_same_parchi_without_a_second_acknowledgement(h):
    """If the first slip is lost, the replacement must work -- and still be one fact."""
    issue = h.open_parchi()
    replacement = issue_acknowledgement_qr(parchi=issue.parchi, now=LATER, tokens=h.tokens)

    outcome = h.confirm(replacement.payload, now=LATER)

    assert outcome.parchi.parchi_id == issue.parchi.parchi_id
    assert outcome.parchi.state is ParchiState.ACKNOWLEDGED
    assert outcome.parchi.acknowledged_by == WORKER


# --- sealing ----------------------------------------------------------------


def test_sealing_freezes_the_record(h):
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)

    sealed = seal_parchi(
        parchi=h.store.get(issue.parchi.parchi_id),
        now=LATER,
        store=h.store,
        audit=h.audit,
    )

    assert sealed.state is ParchiState.SEALED
    assert sealed.sealed_at == LATER
    assert sealed.content_hash is not None
    assert sealed.acknowledged_at == FIXED_NOW, "sealing preserves the confirmation"


def test_a_pending_parchi_cannot_be_sealed(h):
    """Sealing is not reachable without the worker's own confirmation."""
    issue = h.open_parchi()

    with pytest.raises(IllegalParchiTransition):
        seal_parchi(parchi=issue.parchi, now=LATER, store=h.store, audit=h.audit)

    assert h.store.get(issue.parchi.parchi_id).state is ParchiState.PENDING_ACK


def test_sealing_is_idempotent_for_a_retried_workflow_step(h):
    """A Step Functions retry of the seal step must not fail on the second attempt."""
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)
    first = seal_parchi(
        parchi=h.store.get(issue.parchi.parchi_id), now=LATER, store=h.store, audit=h.audit
    )

    second = seal_parchi(parchi=first, now=DAY_AFTER, store=h.store, audit=h.audit)

    assert second.content_hash == first.content_hash
    assert second.sealed_at == first.sealed_at, "the original seal moment is not rewritten"


def test_a_sealed_parchi_cannot_be_acknowledged_again(h):
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)
    sealed = seal_parchi(
        parchi=h.store.get(issue.parchi.parchi_id), now=LATER, store=h.store, audit=h.audit
    )

    replacement = issue_acknowledgement_qr
    with pytest.raises(IllegalParchiTransition):
        replacement(parchi=sealed, now=DAY_AFTER, tokens=h.tokens)


def test_sealing_writes_its_own_audit_event(h):
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)
    sealed = seal_parchi(
        parchi=h.store.get(issue.parchi.parchi_id), now=LATER, store=h.store, audit=h.audit
    )

    seals = h.audit.for_event("ParchiSealed")
    assert len(seals) == 1
    assert seals[0].detail["content_hash"] == sealed.content_hash


def test_a_sealed_record_survives_in_the_store(h):
    issue = h.open_parchi()
    h.confirm(issue.qr.payload)
    seal_parchi(parchi=h.store.get(issue.parchi.parchi_id), now=LATER, store=h.store, audit=h.audit)

    stored = h.store.get(issue.parchi.parchi_id)
    assert stored.state is ParchiState.SEALED
    with pytest.raises(IllegalParchiTransition):
        h.store.save(stored)


# --- describing a pending parchi --------------------------------------------


def test_a_worker_can_see_what_they_are_being_asked_to_confirm(h):
    issue = h.open_parchi()

    view = describe_pending_parchi(
        payload=issue.qr.payload, now=FIXED_NOW, store=h.store, tokens=h.tokens
    )

    assert view.parchi_id == issue.parchi.parchi_id
    assert view.site_id == "site-001"
    assert view.worker_id == WORKER
    assert view.state is ParchiState.PENDING_ACK
    assert view.readiness_checklist == ("Welfare board registration number",)
    assert view.entitlement_refs == ("ent-cited-clause-01",)


def test_the_view_says_when_the_evidence_is_not_a_live_measurement(h):
    issue = h.open_parchi()

    view = describe_pending_parchi(
        payload=issue.qr.payload, now=FIXED_NOW, store=h.store, tokens=h.tokens
    )

    assert view.cites_measured_data is True
    assert view.source_document_ids == (PROVENANCE.stage.order_doc_id,)
    assert view.source_hashes == (PROVENANCE.stage.order_sha256,)


def test_replay_evidence_is_labelled_as_replay_in_the_view(h):
    issue = create_parchi_for_worker(
        parchi_id="parchi-replay",
        execution=EXECUTION,
        worker=RosterEntry(worker_id=WORKER, display_name="Worker A"),
        provenance=ParchiProvenance(
            stage=invoked_stage(), reading=reading(provenance=Provenance.REPLAY)
        ),
        idempotency_key="idem-replay",
        now=FIXED_NOW,
        store=h.store,
        tokens=h.tokens,
    )

    view = describe_pending_parchi(
        payload=issue.qr.payload, now=FIXED_NOW, store=h.store, tokens=h.tokens
    )

    assert view.provenance is Provenance.REPLAY
    assert view.cites_measured_data is False


def test_describing_does_not_acknowledge(h):
    issue = h.open_parchi()

    describe_pending_parchi(payload=issue.qr.payload, now=FIXED_NOW, store=h.store, tokens=h.tokens)

    assert h.store.get(issue.parchi.parchi_id).state is ParchiState.PENDING_ACK
    assert h.tokens.get(issue.qr.token_hash).state.value == "active"


def test_describing_with_an_expired_link_is_refused(h):
    issue = h.open_parchi()
    with pytest.raises(TokenRejected):
        describe_pending_parchi(
            payload=issue.qr.payload, now=DAY_AFTER, store=h.store, tokens=h.tokens
        )


def test_describing_with_a_forged_link_is_refused(h):
    h.open_parchi()
    with pytest.raises(TokenRejected):
        describe_pending_parchi(
            payload=f"{TOKEN_SCHEME}{'C' * 43}", now=FIXED_NOW, store=h.store, tokens=h.tokens
        )


def test_the_view_carries_no_contact_or_identity_document(h):
    """The token holder is already the worker; the view must not hand out anything else."""
    issue = h.open_parchi()
    view = describe_pending_parchi(
        payload=issue.qr.payload, now=FIXED_NOW, store=h.store, tokens=h.tokens
    )

    rendered = repr(view).lower()
    for banned in ("aadhaar", "aadhar", "phone", "mobile", "bank", "ifsc", "address", "pan_"):
        assert banned not in rendered, f"the worker view exposes {banned!r}"


def test_the_payload_round_trips_through_the_parser(h):
    """Scanning the QR and re-deriving the hash must find the token that was minted."""
    issue = h.open_parchi()

    assert hash_token(parse_acknowledgement_payload(issue.qr.payload)) == issue.qr.token_hash
    assert h.tokens.get(issue.qr.token_hash) is not None
