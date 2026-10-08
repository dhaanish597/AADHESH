"""INVARIANT: concurrency does not produce a second acknowledgement, a second parchi, or a
second audit line.

Every idempotency mechanism in this system exists for a specific race, so each one is tested
by actually running the race rather than by reasoning about it:

  * `IdempotencyLedger.execute_once` -- two threads confirming the same link at once
  * `AcknowledgementTokenStore.consume` -- compare-and-set, so the loser loses here
  * `ParchiAckStore.save_new` -- a conditional create, so two concurrent workflow retries
    cannot both open a parchi for the same worker

Threads, not asyncio: the failure mode being defended against is two OS-level requests
arriving together, and a test that cooperatively interleaves coroutines would not exercise
the locks at all.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.domain import ParchiState, Provenance
from aadesh_core.errors import (
    AcknowledgementRejected,
    DuplicateIdempotencyKey,
    TokenRejected,
    TokenRejectionReason,
    WrongWorker,
)
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    RosterEntry,
    WorkflowExecution,
    create_parchi_for_worker,
)
from aadesh_core.parchi_ack.events import EVENT_TYPE_PARCHI_ACKNOWLEDGED
from aadesh_core.parchi_ack.service import acknowledge_parchi
from tests.support.builders import FIXED_NOW, invoked_stage, reading

WORKER = "worker-001"
THREADS = 8

EXECUTION = WorkflowExecution(
    execution_id="exec-race-001",
    site_id="site-001",
    source_event_id="evt-stage-invocation-001",
)

PROVENANCE = ParchiProvenance(
    stage=invoked_stage(),
    reading=reading(provenance=Provenance.MEASURED),
    obligation_ids=("ob-dust-01",),
    entitlement_refs=("ent-cited-clause-01",),
)


def par_both(operation):
    """Run `operation` on THREADS threads at once and return every result."""
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(lambda _: operation(), range(THREADS)))


# --- the ledger -------------------------------------------------------------


def test_execute_once_runs_the_operation_exactly_once_under_contention():
    ledger = InMemoryIdempotencyLedger()
    runs: list[int] = []

    def compute() -> str:
        runs.append(1)
        return "the answer"

    results = par_both(lambda: ledger.execute_once(key="k", compute=compute))

    assert len(runs) == 1, f"the operation ran {len(runs)} times"
    assert set(results) == {"the answer"}


def test_every_later_caller_receives_the_first_result():
    ledger = InMemoryIdempotencyLedger()
    calls: list[int] = []

    def compute() -> int:
        calls.append(1)
        return len(calls)

    ledger.execute_once(key="k", compute=compute)
    assert ledger.execute_once(key="k", compute=compute) == 1
    assert ledger.execute_once(key="k", compute=compute) == 1


def test_different_keys_do_not_block_each_other():
    ledger = InMemoryIdempotencyLedger()
    results = par_both(lambda: ledger.execute_once(key=f"k{id(object())}", compute=lambda: 1))
    assert set(results) == {1}


def test_a_raising_operation_leaves_the_key_unclaimed():
    """A transient failure must not permanently poison the key, or a retry could never run."""
    ledger = InMemoryIdempotencyLedger()

    def boom() -> str:
        raise RuntimeError("transient")

    with pytest.raises(RuntimeError):
        ledger.execute_once(key="k", compute=boom)

    assert ledger.execute_once(key="k", compute=lambda: "recovered") == "recovered"


def test_a_failure_leaves_the_key_claimable_by_the_next_caller():
    """Contention plus failure.

    Nothing is recorded for a failed attempt, so every caller that lost the race to a
    failing operation simply gets the failure and may try again. That is the intended
    behaviour: a genuinely transient error must not poison the key forever, and for
    acknowledgement the failure happens before anything is written.
    """
    ledger = InMemoryIdempotencyLedger()

    def boom() -> str:
        raise RuntimeError("transient")

    def attempt() -> str:
        try:
            return ledger.execute_once(key="k", compute=boom)
        except RuntimeError:
            return "failed"

    assert par_both(attempt) == ["failed"] * THREADS
    assert ledger.execute_once(key="k", compute=lambda: "recovered") == "recovered"


def test_an_empty_key_is_refused():
    ledger = InMemoryIdempotencyLedger()
    with pytest.raises(ValueError, match="key"):
        ledger.execute_once(key="  ", compute=lambda: 1)


# --- the token store --------------------------------------------------------


def test_only_one_thread_can_consume_a_token():
    tokens = InMemoryAcknowledgementTokenStore()
    store = InMemoryParchiStore()
    issue = create_parchi_for_worker(
        parchi_id="parchi-001",
        execution=EXECUTION,
        worker=RosterEntry(worker_id=WORKER, display_name="Worker A"),
        provenance=PROVENANCE,
        idempotency_key="idem-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )
    assert issue.qr is not None
    token_hash = issue.qr.token_hash

    def consume() -> str:
        try:
            tokens.consume(token_hash, at=FIXED_NOW, event_id="evt-1")
        except TokenRejected as exc:
            return exc.reason.value
        return "won"

    results = par_both(consume)

    assert results.count("won") == 1, f"the token was consumed {results.count('won')} times"
    assert results.count(TokenRejectionReason.CONSUMED.value) == THREADS - 1


# --- the acknowledgement path ----------------------------------------------

CONFIRM_EXECUTION = WorkflowExecution(
    execution_id="exec-race-ack",
    site_id="site-001",
    source_event_id="evt-stage-invocation-002",
)


def _ack_harness():
    store = InMemoryParchiStore()
    tokens = InMemoryAcknowledgementTokenStore()
    ledger = InMemoryIdempotencyLedger()
    audit = RecordingAuditLog()
    issue = create_parchi_for_worker(
        parchi_id="parchi-race-ack",
        execution=CONFIRM_EXECUTION,
        worker=RosterEntry(worker_id=WORKER, display_name="Worker A"),
        provenance=PROVENANCE,
        idempotency_key="idem-race-ack",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )
    assert issue.qr is not None
    return store, tokens, ledger, audit, issue.qr.payload


def test_simultaneous_confirmations_produce_one_acknowledgement():
    """The double-tap race, and the reason the operation is memoised rather than retried."""
    store, tokens, ledger, audit, payload = _ack_harness()

    def confirm():
        return acknowledge_parchi(
            payload=payload,
            actor_worker_id=WORKER,
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
        )

    outcomes = par_both(confirm)

    assert len(audit.for_event(EVENT_TYPE_PARCHI_ACKNOWLEDGED)) == 1
    assert len({o.event.event_id for o in outcomes}) == 1
    assert len({o.parchi.acknowledged_at for o in outcomes}) == 1
    assert store.get("parchi-race-ack").state is ParchiState.ACKNOWLEDGED


def test_no_outcome_from_a_race_hands_back_a_second_confirmation():
    store, tokens, ledger, audit, payload = _ack_harness()

    def confirm():
        return acknowledge_parchi(
            payload=payload,
            actor_worker_id=WORKER,
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
        )

    outcomes = par_both(confirm)

    # Exactly one caller did the work. The others were handed its result -- which is not the
    # same as having done it, and the flag says so.
    assert sum(1 for o in outcomes if not o.already_confirmed) == 1


def test_a_wrong_worker_racing_the_real_one_leaves_the_link_usable():
    store, tokens, ledger, audit, payload = _ack_harness()

    def attempt(who: str):
        try:
            return acknowledge_parchi(
                payload=payload,
                actor_worker_id=who,
                now=FIXED_NOW,
                store=store,
                tokens=tokens,
                ledger=ledger,
                audit=audit,
            )
        except AcknowledgementRejected as exc:
            return exc

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(attempt, ["worker-002"] * (THREADS - 1) + [WORKER]))

    # Every colleague is refused, and the one real worker still gets through -- racing a
    # refusal must not cost the worker their confirmation.
    refusals = [r for r in results if isinstance(r, AcknowledgementRejected)]
    successes = [r for r in results if not isinstance(r, AcknowledgementRejected)]

    assert len(refusals) == THREADS - 1
    assert all(isinstance(r, WrongWorker) for r in refusals)
    assert len(successes) == 1
    assert store.get("parchi-race-ack").state is ParchiState.ACKNOWLEDGED
    assert store.get("parchi-race-ack").acknowledged_by == WORKER
    assert len(audit.for_event(EVENT_TYPE_PARCHI_ACKNOWLEDGED)) == 1


# --- the creation path ------------------------------------------------------


class WinnerLandsMidCall(InMemoryParchiStore):
    """A store that reproduces the losing side of a creation race, deterministically.

    The hazard: two workflow retries both look up the idempotency key, both miss (neither has
    written yet), and both proceed to create. Threads alone rarely reproduce it -- the window
    is microseconds wide and the GIL closes it by accident -- so this store forces the exact
    interleaving instead of hoping for it: the first lookup misses, and the competing caller's
    write lands immediately afterwards.
    """

    def __init__(self, winner) -> None:
        super().__init__()
        self._winner = winner
        self._interleaved = False

    def find_by_idempotency_key(self, idempotency_key: str):
        if not self._interleaved:
            self._interleaved = True
            super().save(self._winner)  # the other caller finishes writing, right here
            return None  # ...but we had already looked, and saw nothing
        return super().find_by_idempotency_key(idempotency_key)


def _winner_parchi():
    from aadesh_core.parchi import issue, open_parchi

    return issue(
        open_parchi(
            parchi_id="parchi-winner",
            site_id=EXECUTION.site_id,
            worker_id=WORKER,
            stage=PROVENANCE.stage,
            reading=PROVENANCE.reading,
            obligation_ids=PROVENANCE.obligation_ids,
            entitlement_refs=PROVENANCE.entitlement_refs,
            readiness_checklist=(),
            displaced_worker_days=1,
            now=FIXED_NOW,
            workflow_execution_id=EXECUTION.execution_id,
            source_event_id=EXECUTION.source_event_id,
            idempotency_key="idem-lost-race",
        ),
        now=FIXED_NOW,
    )


def test_the_store_refuses_a_second_parchi_for_the_same_key():
    """The conditional create. This is what makes creation idempotent rather than lucky."""
    store = InMemoryParchiStore()
    first = _winner_parchi()
    store.save_new(first)

    with pytest.raises(DuplicateIdempotencyKey):
        store.save_new(replace(first, parchi_id="parchi-second"))

    assert store.find_by_idempotency_key("idem-lost-race").parchi_id == "parchi-winner"
    assert len(store.for_site(EXECUTION.site_id)) == 1


def test_the_store_allows_a_second_parchi_under_a_different_key():
    store = InMemoryParchiStore()
    first = _winner_parchi()
    store.save_new(first)
    store.save_new(replace(first, parchi_id="parchi-other", idempotency_key="idem-other"))

    assert len(store.for_site(EXECUTION.site_id)) == 2


def test_a_creation_that_loses_the_race_returns_the_winner():
    """The loser must NOT create a second parchi, and must not report success either.

    This is the case the conditional create exists for, and it is deliberately not solved by
    catching an error after inserting a duplicate: the conditional create means the duplicate
    insert never happens at all. What is caught is the refusal of that insert, and the caller
    then reads back the record that won.
    """
    winner = _winner_parchi()
    store = WinnerLandsMidCall(winner)
    tokens = InMemoryAcknowledgementTokenStore()

    result = create_parchi_for_worker(
        parchi_id="parchi-loser",
        execution=EXECUTION,
        worker=RosterEntry(worker_id=WORKER, display_name="Worker A"),
        provenance=PROVENANCE,
        idempotency_key="idem-lost-race",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )

    assert result.parchi.parchi_id == "parchi-winner"
    assert result.replayed is True
    assert result.qr is None, "the loser must not mint a second link"
    assert len(store.for_site(EXECUTION.site_id)) == 1


def test_concurrent_creation_opens_one_parchi():
    """A smoke test over real threads. The proof is the two tests above; this one checks the
    wiring under actual contention, where a broken lock would show up intermittently."""
    store = InMemoryParchiStore()
    tokens = InMemoryAcknowledgementTokenStore()

    def create():
        return create_parchi_for_worker(
            parchi_id="parchi-concurrent",
            execution=EXECUTION,
            worker=RosterEntry(worker_id=WORKER, display_name="Worker A"),
            provenance=PROVENANCE,
            idempotency_key="idem-concurrent",
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
        )

    results = par_both(create)

    assert len(store.for_site("site-001")) == 1
    assert {r.parchi.parchi_id for r in results} == {"parchi-concurrent"}
    assert sum(1 for r in results if not r.replayed) == 1


def test_concurrent_creation_hands_out_exactly_one_link():
    """Two live links for one parchi would mean two things a worker could confirm."""
    store = InMemoryParchiStore()
    tokens = InMemoryAcknowledgementTokenStore()

    def create():
        return create_parchi_for_worker(
            parchi_id="parchi-concurrent-2",
            execution=EXECUTION,
            worker=RosterEntry(worker_id=WORKER, display_name="Worker A"),
            provenance=PROVENANCE,
            idempotency_key="idem-concurrent-2",
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
        )

    results = par_both(create)

    assert sum(1 for r in results if r.qr is not None) == 1
