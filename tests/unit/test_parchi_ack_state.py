"""INVARIANT: acknowledgement and sealing are two separate, explicit acts.

The lifecycle Aadesh commits to is:

    DRAFT --issue--> PENDING_ACK --acknowledge--> ACKNOWLEDGED --seal--> SEALED

Collapsing acknowledge+seal into one transition was the earlier design, and Prompt 5
splits them for a specific reason: there is a window in which a worker HAS confirmed a
halt that displaced them, and the record has not yet been frozen. Both moments have to be
observable and both have to be provable, otherwise "the worker confirmed it at 11:04" and
"the evidence was frozen at 11:04" are the same fact and neither can be audited.

Two rules stay load-bearing, exactly as before:

  * **Only the worker named on the parchi may acknowledge it.**
  * **SEALED is terminal and immutable.**
"""

from __future__ import annotations

import dataclasses

import pytest

from aadesh_core.domain import AcknowledgementMethod, ParchiState
from aadesh_core.errors import IllegalParchiTransition
from aadesh_core.parchi import acknowledge, issue, open_parchi, seal, void
from tests.support.builders import FIXED_NOW, invoked_stage, reading

LATER = FIXED_NOW.replace(hour=11)
LATER_STILL = FIXED_NOW.replace(hour=12)


def a_draft(**over):
    return open_parchi(
        parchi_id=over.get("parchi_id", "parchi-001"),
        site_id="site-001",
        worker_id=over.get("worker_id", "worker-001"),
        stage=invoked_stage(),
        reading=over.get("reading", reading()),
        obligation_ids=("ob-1",),
        entitlement_refs=(),
        readiness_checklist=("Welfare board registration number",),
        displaced_worker_days=1,
        now=FIXED_NOW,
    )


def a_pending():
    return issue(a_draft(), now=FIXED_NOW)


def an_acknowledged():
    return acknowledge(a_pending(), actor_worker_id="worker-001", now=LATER)


def a_sealed():
    return seal(an_acknowledged(), now=LATER_STILL)


# --- PENDING_ACK -> ACKNOWLEDGED -------------------------------------------


def test_acknowledge_moves_pending_ack_to_acknowledged_not_sealed():
    acked = an_acknowledged()
    assert acked.state is ParchiState.ACKNOWLEDGED


def test_acknowledge_records_who_and_when_and_how():
    acked = an_acknowledged()
    assert acked.acknowledged_at == LATER
    assert acked.acknowledged_by == "worker-001"
    assert acked.acknowledgement_method is AcknowledgementMethod.QR_CONFIRMED


def test_acknowledge_does_not_seal():
    """Acknowledging is not sealing. The evidence hash appears only at seal time."""
    acked = an_acknowledged()
    assert acked.sealed_at is None
    assert acked.content_hash is None


def test_acknowledged_is_not_terminal():
    assert an_acknowledged().is_terminal is False


# --- ACKNOWLEDGED -> SEALED ------------------------------------------------


def test_seal_moves_acknowledged_to_sealed():
    assert a_sealed().state is ParchiState.SEALED


def test_seal_records_the_sealing_moment():
    sealed = a_sealed()
    assert sealed.sealed_at == LATER_STILL
    assert sealed.content_hash is not None
    assert len(sealed.content_hash) == 64


def test_seal_preserves_the_acknowledgement_it_froze():
    sealed = a_sealed()
    assert sealed.acknowledged_at == LATER
    assert sealed.acknowledged_by == "worker-001"
    assert sealed.acknowledgement_method is AcknowledgementMethod.QR_CONFIRMED


def test_seal_is_deterministic():
    assert a_sealed().content_hash == a_sealed().content_hash


def test_content_hash_covers_the_acknowledgement():
    """Re-sealing the same parchi with a different acknowledgement must not collide.

    The acknowledgement fields are inside the hash, so an attempt to freeze a parchi while
    claiming a different acknowledging worker produces a different digest.
    """
    other = seal(
        acknowledge(a_pending(), actor_worker_id="worker-001", now=LATER_STILL),
        now=LATER_STILL,
    )
    assert other.content_hash != a_sealed().content_hash


def test_sealed_is_terminal():
    assert a_sealed().is_terminal is True


# --- invalid transitions fail deterministically -----------------------------


@pytest.mark.parametrize(
    ("transition", "from_state"),
    [
        # Nothing seals before a worker has confirmed it.
        ("seal", "pending"),
        ("seal", "draft"),
        # SEALED is terminal: sealing it again is not a no-op, it is an error.
        ("seal", "sealed"),
        # ACKNOWLEDGED may only go forward to SEALED (or be voided).
        ("acknowledge", "acknowledged"),
        ("issue", "acknowledged"),
    ],
)
def test_illegal_transitions_involving_the_new_states_raise(transition, from_state):
    """The transitions the pre-existing lifecycle table could not cover.

    `test_parchi_lifecycle.py` keeps the original table (draft/pending/sealed/void); these
    are the rows that only exist now that ACKNOWLEDGED and `seal` do.
    """
    parchi = {
        "draft": a_draft,
        "pending": a_pending,
        "acknowledged": an_acknowledged,
        "sealed": a_sealed,
    }[from_state]()
    fn = {"acknowledge": acknowledge, "issue": issue, "seal": seal}[transition]
    kwargs = {"actor_worker_id": "worker-001"} if transition == "acknowledge" else {}

    with pytest.raises(IllegalParchiTransition):
        fn(parchi, now=LATER, **kwargs)


def test_void_from_acknowledged_is_allowed():
    """A site that reopened before the record was frozen can still be cancelled."""
    voided = void(an_acknowledged(), reason="Site reopened early", now=LATER_STILL)
    assert voided.state is ParchiState.VOID


# --- the security invariants, unchanged ------------------------------------


def test_supervisor_cannot_acknowledge_on_a_workers_behalf():
    with pytest.raises(IllegalParchiTransition, match="only the worker named"):
        acknowledge(a_pending(), actor_worker_id="supervisor-001", now=LATER)


def test_another_worker_cannot_acknowledge_it_either():
    with pytest.raises(IllegalParchiTransition):
        acknowledge(a_pending(), actor_worker_id="worker-002", now=LATER)


def test_a_worker_who_did_not_acknowledge_cannot_seal_on_their_behalf():
    """Sealing is a system act, but it cannot be used to mint an acknowledgement.

    There is no path that produces SEALED without a preceding ACKNOWLEDGED, so a supervisor
    cannot reach a sealed record by sealing a pending one.
    """
    with pytest.raises(IllegalParchiTransition):
        seal(a_pending(), now=LATER)


def test_a_sealed_parchi_cannot_be_mutated():
    sealed = a_sealed()
    with pytest.raises(dataclasses.FrozenInstanceError):
        sealed.worker_id = "worker-002"  # type: ignore[misc]


def test_no_api_exists_to_edit_a_sealed_parchi():
    """There is deliberately no `edit`. Correction is a new event, not a mutation."""
    import aadesh_core.parchi as parchi_module

    for forbidden in ("edit", "update", "amend", "correct"):
        assert not hasattr(parchi_module, forbidden), (
            f"aadesh_core.parchi exposes {forbidden!r}; sealed evidence must be correctable "
            f"only by appending a new event, never by mutating the record."
        )


def test_transitions_return_new_objects_rather_than_mutating():
    acked = an_acknowledged()
    sealed = seal(acked, now=LATER_STILL)
    assert acked.state is ParchiState.ACKNOWLEDGED
    assert sealed is not acked
