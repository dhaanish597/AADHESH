"""INVARIANT: a workflow opens one parchi per displaced worker, exactly once, provably.

This is the seam Prompt 4's standing-order machine will call. It is written against a small
domain interface rather than against Prompt 4's unfinished code, so it is testable now and
usable later without guessing at what that machine will look like.

The four things this file pins down:

  * creation is keyed, so replaying a workflow step does not mint a second parchi
  * the provenance a parchi carries is the provenance it was given, byte for byte
  * the roster is a roster, and worker COUNT is never turned into a legal conclusion
  * nothing here needs a model, and nothing here invents a rupee figure
"""

from __future__ import annotations

import pytest

from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.domain import ParchiState, Provenance
from aadesh_core.errors import IllegalParchiTransition
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    Roster,
    RosterEntry,
    WorkflowExecution,
    create_parchi_for_worker,
    create_parchis_for_roster,
    issue_acknowledgement_qr,
)
from tests.support.builders import FIXED_NOW, invoked_stage, reading

REPLAY_READING = reading(provenance=Provenance.REPLAY)

EXECUTION = WorkflowExecution(
    execution_id="exec-2026-10-08-001",
    site_id="site-001",
    source_event_id="evt-stage-invocation-001",
)

PROVENANCE = ParchiProvenance(
    stage=invoked_stage(),
    reading=REPLAY_READING,
    obligation_ids=("ob-dust-01",),
    entitlement_refs=("ent-cited-clause-01",),
    readiness_checklist=("Welfare board registration number",),
    displaced_worker_days=3,
)

ROSTER = Roster(
    site_id="site-001",
    entries=(
        RosterEntry(worker_id="worker-001", display_name="Worker A"),
        RosterEntry(worker_id="worker-002", display_name="Worker B"),
        RosterEntry(worker_id="worker-003", display_name="Worker C", active=False),
    ),
)


@pytest.fixture
def store() -> InMemoryParchiStore:
    return InMemoryParchiStore()


@pytest.fixture
def tokens() -> InMemoryAcknowledgementTokenStore:
    return InMemoryAcknowledgementTokenStore()


@pytest.fixture
def ledger() -> InMemoryIdempotencyLedger:
    return InMemoryIdempotencyLedger()


def create(store, tokens, *, worker_id="worker-001", key="idem-001", now=FIXED_NOW, **over):
    return create_parchi_for_worker(
        parchi_id=over.pop("parchi_id", f"parchi-{worker_id}"),
        execution=EXECUTION,
        worker=RosterEntry(worker_id=worker_id, display_name="Worker A"),
        provenance=over.pop("provenance", PROVENANCE),
        idempotency_key=key,
        now=now,
        store=store,
        tokens=tokens,
    )


# --- A. creation -----------------------------------------------------------


def test_a_workflow_creates_a_pending_ack_parchi(store, tokens):
    issue = create(store, tokens)

    assert issue.parchi.state is ParchiState.PENDING_ACK
    assert issue.replayed is False
    assert store.get(issue.parchi.parchi_id) is not None


def test_creation_returns_a_qr_the_worker_can_actually_use(store, tokens):
    issue = create(store, tokens)

    assert issue.qr is not None
    assert issue.qr.payload.startswith("aadesh://ack/")
    stored = tokens.get(issue.qr.token_hash)
    assert stored is not None
    assert stored.parchi_id == issue.parchi.parchi_id
    assert stored.worker_id == issue.parchi.worker_id


def test_the_qr_is_not_part_of_the_parchi_record(store, tokens):
    """The parchi stores a reference derived from the token hash, never the payload."""
    issue = create(store, tokens)
    raw = issue.qr.payload

    assert raw not in repr(issue.parchi)
    assert issue.parchi.acknowledgement_token_ref is None, "no token reference until acked"


# --- A/G. idempotent creation ----------------------------------------------


def test_replaying_creation_with_the_same_key_does_not_duplicate_the_parchi(store, tokens):
    first = create(store, tokens, key="idem-001")
    second = create(store, tokens, key="idem-001")

    assert second.replayed is True
    assert second.parchi.parchi_id == first.parchi.parchi_id
    assert second.parchi.created_at == first.parchi.created_at
    assert len(store.for_site("site-001")) == 1


def test_a_replayed_creation_does_not_hand_out_a_second_qr(store, tokens):
    """The raw token is unrecoverable by design, so a replay cannot re-issue the same one.

    Minting a fresh token here would leave two live links for one parchi. The honest answer
    is `None`, and `issue_acknowledgement_qr` is the explicit act that mints a new one.
    """
    create(store, tokens, key="idem-001")
    second = create(store, tokens, key="idem-001")

    assert second.qr is None


def test_creation_is_idempotent_across_different_now_values(store, tokens):
    """A retry arrives later than the original. That must not change the outcome."""
    first = create(store, tokens, key="idem-001", now=FIXED_NOW)
    second = create(store, tokens, key="idem-001", now=FIXED_NOW.replace(hour=23))

    assert second.replayed is True
    assert second.parchi.created_at == first.parchi.created_at


def test_a_different_key_creates_a_different_parchi(store, tokens):
    first = create(store, tokens, key="idem-001", parchi_id="parchi-a")
    second = create(store, tokens, key="idem-002", parchi_id="parchi-b")

    assert second.replayed is False
    assert second.parchi.parchi_id != first.parchi.parchi_id
    assert len(store.for_site("site-001")) == 2


def test_the_idempotency_key_is_preserved_on_the_record(store, tokens):
    issue = create(store, tokens, key="idem-001")
    assert issue.parchi.idempotency_key == "idem-001"


def test_the_store_can_find_a_parchi_by_its_idempotency_key(store, tokens):
    issue = create(store, tokens, key="idem-001")
    assert store.find_by_idempotency_key("idem-001").parchi_id == issue.parchi.parchi_id
    assert store.find_by_idempotency_key("idem-nope") is None


# --- G. provenance is carried, not recomputed ------------------------------


def test_the_workflow_and_source_event_are_preserved(store, tokens):
    issue = create(store, tokens)
    parchi = issue.parchi

    assert parchi.workflow_execution_id == "exec-2026-10-08-001"
    assert parchi.source_event_id == "evt-stage-invocation-001"
    assert parchi.site_id == "site-001"


def test_the_stage_and_reading_provenance_reach_the_parchi(store, tokens):
    parchi = create(store, tokens).parchi

    assert parchi.stage is PROVENANCE.stage
    assert parchi.order_sha256 == PROVENANCE.stage.order_sha256
    assert parchi.reading is REPLAY_READING
    assert parchi.provenance is Provenance.REPLAY
    assert parchi.cites_measured_data is False


def test_the_evidence_references_are_preserved(store, tokens):
    parchi = create(store, tokens).parchi

    assert parchi.obligation_ids == ("ob-dust-01",)
    assert parchi.entitlement_refs == ("ent-cited-clause-01",)
    assert parchi.readiness_checklist == ("Welfare board registration number",)
    assert parchi.displaced_worker_days == 3


def test_the_parchi_records_which_documents_it_rests_on(store, tokens):
    parchi = create(store, tokens).parchi

    assert parchi.source_document_ids == (PROVENANCE.stage.order_doc_id,)
    assert parchi.source_hashes == (PROVENANCE.stage.order_sha256,)


def test_the_schema_version_is_stamped(store, tokens):
    assert create(store, tokens).parchi.schema_version == "parchi/2"


# --- roster ----------------------------------------------------------------


def test_a_roster_creates_one_parchi_per_active_worker(store, tokens):
    issues = create_parchis_for_roster(
        execution=EXECUTION,
        roster=ROSTER,
        provenance=PROVENANCE,
        idempotency_key="idem-roster-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )

    assert len(issues) == 2, "the inactive entry is not displaced by this halt"
    assert {i.parchi.worker_id for i in issues} == {"worker-001", "worker-002"}
    assert all(p.state is ParchiState.PENDING_ACK for p in store.for_site("site-001"))


def test_a_roster_creation_is_idempotent(store, tokens):
    for _ in range(3):
        create_parchis_for_roster(
            execution=EXECUTION,
            roster=ROSTER,
            provenance=PROVENANCE,
            idempotency_key="idem-roster-001",
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
        )

    assert len(store.for_site("site-001")) == 2


def test_parchi_ids_from_a_roster_are_derived_deterministically(store, tokens):
    """So a retry addresses the same records rather than inventing new ones."""
    first = create_parchis_for_roster(
        execution=EXECUTION,
        roster=ROSTER,
        provenance=PROVENANCE,
        idempotency_key="idem-roster-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )
    ids = [i.parchi.parchi_id for i in first]

    assert len(set(ids)) == len(ids), "each worker gets their own parchi id"
    assert all("exec-2026-10-08-001" in i for i in ids)


def test_a_roster_entry_must_belong_to_the_executions_site(store, tokens):
    foreign = Roster(
        site_id="site-999",
        entries=(RosterEntry(worker_id="worker-001", display_name="Worker A"),),
    )
    with pytest.raises(ValueError, match="site"):
        create_parchis_for_roster(
            execution=EXECUTION,
            roster=foreign,
            provenance=PROVENANCE,
            idempotency_key="idem-roster-002",
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
        )


# --- issuing a (re)placement QR --------------------------------------------


def test_a_qr_can_be_reissued_for_a_pending_parchi(store, tokens):
    parchi = create(store, tokens).parchi
    qr = issue_acknowledgement_qr(parchi=parchi, now=FIXED_NOW, tokens=tokens)

    assert qr.payload.startswith("aadesh://ack/")
    assert tokens.get(qr.token_hash).worker_id == parchi.worker_id


def test_a_sealed_parchi_cannot_be_given_a_new_qr(store, tokens):
    """Otherwise a sealed record could be 're-acknowledged' through a fresh link."""
    from aadesh_core.parchi import acknowledge, seal

    pending = create(store, tokens).parchi
    sealed = seal(acknowledge(pending, actor_worker_id="worker-001", now=FIXED_NOW), now=FIXED_NOW)

    with pytest.raises(IllegalParchiTransition):
        issue_acknowledgement_qr(parchi=sealed, now=FIXED_NOW, tokens=tokens)


# --- H. safety: no entitlement is invented ---------------------------------


def test_creation_invents_no_monetary_entitlement(store, tokens):
    """No figure is computed, stored or implied anywhere on the record."""
    parchi = create(store, tokens).parchi

    for field in ("amount_inr", "entitlement_amount", "compensation", "rupees", "value_inr"):
        assert not hasattr(parchi, field), (
            f"Parchi exposes {field!r}. There is no verified monetary entitlement in the "
            f"corpus, so the record must not be able to carry an invented one."
        )
    # entitlement_refs are REFERENCES to cited clauses, never amounts.
    assert all(isinstance(ref, str) for ref in parchi.entitlement_refs)


def test_worker_count_does_not_produce_a_legal_claim(store, tokens):
    """Three workers displaced is three records, not a multiplier on a rupee figure.

    `displaced_worker_days` is copied from the provenance it was GIVEN; it is never derived
    by multiplying workers by days, because that would be the system asserting an amount
    nobody cited.
    """
    issues = create_parchis_for_roster(
        execution=EXECUTION,
        roster=ROSTER,
        provenance=PROVENANCE,
        idempotency_key="idem-roster-003",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )

    assert len(issues) == 2
    assert all(i.parchi.displaced_worker_days == PROVENANCE.displaced_worker_days for i in issues)


def test_an_inactive_roster_entry_is_not_a_compliance_or_entitlement_judgment():
    """`active` means roster bookkeeping. It is not eligibility, and it is documented as such."""
    entry = RosterEntry(worker_id="worker-003", display_name="Worker C", active=False)
    assert entry.active is False
    assert RosterEntry.__doc__ is not None
    assert "eligib" in Roster.__doc__.lower()
