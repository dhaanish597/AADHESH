"""INVARIANT: illegal parchi transitions fail loudly.

A parchi is evidence. Its lifecycle encodes two product commitments:

  * **Only the named worker can complete it.** The halt record is incomplete until the
    people it displaced have confirmed it themselves. Cedar enforces this at the
    authorization boundary; the domain enforces it again here, because a boundary that is
    only checked in one place is a boundary one refactor away from not existing.
  * **SEALED is terminal and immutable.** Evidence that can be edited after the fact is not
    evidence.
"""

from __future__ import annotations

import dataclasses

import pytest

from aadesh_core.domain import ParchiState, Provenance
from aadesh_core.errors import IllegalParchiTransition
from aadesh_core.parchi import acknowledge, issue, open_parchi, void
from tests.support.builders import FIXED_NOW, invoked_stage, reading

LATER = FIXED_NOW.replace(hour=11)


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


def a_sealed():
    return acknowledge(a_pending(), actor_worker_id="worker-001", now=LATER)


# --- the happy path --------------------------------------------------------


def test_open_creates_a_draft():
    assert a_draft().state is ParchiState.DRAFT


def test_issue_moves_draft_to_pending_ack():
    assert issue(a_draft(), now=FIXED_NOW).state is ParchiState.PENDING_ACK


def test_worker_acknowledging_their_own_parchi_seals_it():
    sealed = a_sealed()
    assert sealed.state is ParchiState.SEALED
    assert sealed.acknowledged_at == LATER
    assert sealed.acknowledged_by == "worker-001"
    assert sealed.sealed_at == LATER


def test_sealing_computes_a_content_hash():
    sealed = a_sealed()
    assert sealed.content_hash is not None
    assert len(sealed.content_hash) == 64


def test_content_hash_is_deterministic():
    assert a_sealed().content_hash == a_sealed().content_hash


def test_content_hash_changes_when_evidentiary_content_differs():
    other = acknowledge(
        issue(a_draft(parchi_id="parchi-002"), now=FIXED_NOW),
        actor_worker_id="worker-001",
        now=LATER,
    )
    assert a_sealed().content_hash != other.content_hash


def test_void_from_pending_ack_is_allowed():
    voided = void(a_pending(), reason="Site reopened early", now=LATER)
    assert voided.state is ParchiState.VOID
    assert voided.void_reason == "Site reopened early"


# --- the invariant ---------------------------------------------------------


def test_supervisor_cannot_acknowledge_on_a_workers_behalf():
    """Defence in depth. Cedar denies this at the boundary; the domain refuses it too."""
    with pytest.raises(IllegalParchiTransition, match="only the worker named"):
        acknowledge(a_pending(), actor_worker_id="supervisor-001", now=LATER)


def test_another_worker_cannot_acknowledge_it_either():
    with pytest.raises(IllegalParchiTransition):
        acknowledge(a_pending(), actor_worker_id="worker-002", now=LATER)


@pytest.mark.parametrize(
    ("transition", "from_state", "kwargs"),
    [
        ("acknowledge", "draft", {"actor_worker_id": "worker-001"}),
        ("acknowledge", "sealed", {"actor_worker_id": "worker-001"}),
        ("acknowledge", "void", {"actor_worker_id": "worker-001"}),
        ("issue", "pending", {}),
        ("issue", "sealed", {}),
        ("issue", "void", {}),
        ("void", "sealed", {"reason": "any"}),
        ("void", "void", {"reason": "any"}),
    ],
)
def test_illegal_transitions_raise(transition, from_state, kwargs):
    parchi = {
        "draft": a_draft,
        "pending": a_pending,
        "sealed": a_sealed,
        "void": lambda: void(a_pending(), reason="x", now=LATER),
    }[from_state]()
    fn = {"acknowledge": acknowledge, "issue": issue, "void": void}[transition]

    with pytest.raises(IllegalParchiTransition):
        fn(parchi, now=LATER, **kwargs)


def test_a_sealed_parchi_cannot_be_mutated():
    sealed = a_sealed()
    with pytest.raises(dataclasses.FrozenInstanceError):
        sealed.worker_id = "worker-002"  # type: ignore[misc]


def test_sealed_parchi_retains_the_order_hash_it_was_issued_under():
    sealed = a_sealed()
    assert sealed.order_sha256 == invoked_stage().order_sha256


def test_transitions_return_new_objects_rather_than_mutating():
    draft = a_draft()
    issued = issue(draft, now=FIXED_NOW)
    assert draft.state is ParchiState.DRAFT
    assert issued is not draft


def test_provenance_is_carried_from_the_reading():
    assert a_draft().provenance is Provenance.SYNTHETIC
