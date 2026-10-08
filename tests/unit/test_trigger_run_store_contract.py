"""Contract test for TriggerRunStore.

The idempotency guarantee is this contract, not a flag. A fake satisfying the protocol is the
test double used by the full-chain test; the future DynamoDB adapter is held to the same
contract.

The single chokepoint is `claim`: create-if-absent, and MUST return the EXISTING run when one is
present, MUST NOT overwrite it. A redelivery of the same trigger is a clean no-op that reports
the original parchi ids.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import TriggerRun
from aadesh_core.standing_order.ports import TriggerRunStore


class FakeTriggerRunStore(TriggerRunStore):
    """An in-memory store that satisfies TriggerRunStore exactly.

    Used by tests and by the full-chain test. The contract it implements is the same one the
    DynamoDB adapter must satisfy: claim returns the existing run on collision, and never
    overwrites.
    """

    def __init__(self) -> None:
        self._runs: dict[str, TriggerRun] = {}

    def claim(self, run: TriggerRun) -> TriggerRun:
        existing = self._runs.get(run.fingerprint)
        if existing is not None:
            return existing
        self._runs[run.fingerprint] = run
        return run

    def get(self, fingerprint: str) -> TriggerRun | None:
        return self._runs.get(fingerprint)

    def complete(self, fingerprint: str, *, completed_at: datetime | None = None) -> None:
        existing = self._runs.get(fingerprint)
        if existing is None:
            return
        # Idempotent: if already COMPLETED, do nothing.
        if existing.status is StandingOrderStatus.COMPLETED:
            return
        completed = TriggerRun(
            fingerprint=existing.fingerprint,
            standing_order_id=existing.standing_order_id,
            site_id=existing.site_id,
            stage=existing.stage,
            order_doc_id=existing.order_doc_id,
            order_sha256=existing.order_sha256,
            started_at=existing.started_at,
            status=StandingOrderStatus.COMPLETED,
            parchi_ids=existing.parchi_ids,
            completed_at=completed_at or datetime.now(tz=UTC),
        )
        self._runs[fingerprint] = completed


def _run(
    *,
    fingerprint: str = "fp-1",
    status: StandingOrderStatus = StandingOrderStatus.TRIGGERED,
    parchi_ids: tuple[str, ...] | None = None,
) -> TriggerRun:
    if parchi_ids is None:
        parchi_ids = (f"parchi-{fingerprint}-w1",)
    return TriggerRun(
        fingerprint=fingerprint,
        standing_order_id="so-1",
        site_id="site-001",
        stage=3,
        order_doc_id="order-001",
        order_sha256="a" * 64,
        started_at=datetime(2026, 10, 8, 12, 0, tzinfo=UTC),
        status=status,
        parchi_ids=parchi_ids,
    )


def test_claim_creates_a_run_when_none_exists() -> None:
    store = FakeTriggerRunStore()
    run = _run()
    claimed = store.claim(run)
    assert claimed.fingerprint == run.fingerprint
    assert store.get(run.fingerprint) is claimed
    assert claimed is run


def test_claim_returns_the_existing_run_on_collision() -> None:
    store = FakeTriggerRunStore()
    original = _run(fingerprint="fp-1", parchi_ids=("original-parchi",))
    store.claim(original)
    collision = _run(fingerprint="fp-1", parchi_ids=("different-parchi",))
    claimed = store.claim(collision)
    assert claimed.fingerprint == "fp-1"
    assert claimed.parchi_ids == ("original-parchi",)
    assert claimed is original
    assert store.get("fp-1") is original


def test_claim_does_not_overwrite_the_existing_parchi_ids() -> None:
    store = FakeTriggerRunStore()
    original = _run(fingerprint="fp-1", parchi_ids=("parchi-a",))
    store.claim(original)
    collision = _run(fingerprint="fp-1", parchi_ids=("parchi-b", "parchi-c"))
    claimed = store.claim(collision)
    assert claimed.parchi_ids == ("parchi-a",)
    # The store must still hold the original run, not the collision.
    assert store.get("fp-1") is original


def test_claim_is_idempotent() -> None:
    store = FakeTriggerRunStore()
    run = _run()
    first = store.claim(run)
    second = store.claim(run)
    assert first is second
    assert store.get(run.fingerprint) is first


def test_get_returns_none_for_unknown_fingerprint() -> None:
    store = FakeTriggerRunStore()
    assert store.get("unknown") is None


def test_complete_marks_the_run_completed() -> None:
    store = FakeTriggerRunStore()
    run = _run()
    store.claim(run)
    store.complete(run.fingerprint, completed_at=datetime(2026, 10, 8, 12, 5, tzinfo=UTC))
    completed = store.get(run.fingerprint)
    assert completed is not None
    assert completed.status is StandingOrderStatus.COMPLETED
    assert completed.completed_at == datetime(2026, 10, 8, 12, 5, tzinfo=UTC)
    assert completed.parchi_ids == run.parchi_ids


def test_complete_is_idempotent() -> None:
    store = FakeTriggerRunStore()
    run = _run()
    store.claim(run)
    store.complete(run.fingerprint)
    store.complete(run.fingerprint)
    completed = store.get(run.fingerprint)
    assert completed is not None
    assert completed.status is StandingOrderStatus.COMPLETED


def test_complete_is_idempotent_on_a_run_that_was_already_completed() -> None:
    """A double-complete must not resurrect a run or change its parchi ids."""
    store = FakeTriggerRunStore()
    run = _run()
    store.claim(run)
    store.complete(run.fingerprint)
    completed = store.get(run.fingerprint)
    assert completed is not None
    assert completed.status is StandingOrderStatus.COMPLETED
    store.complete(run.fingerprint)
    again = store.get(run.fingerprint)
    assert again is completed
    assert again.parchi_ids == run.parchi_ids


def test_claim_contract_holds_for_a_redelivered_trigger() -> None:
    """A redelivery of the same trigger is a clean no-op: claim returns the original run and
    creates nothing. Parchi ids are deterministic from (fingerprint, worker_id), so even a
    bypass can only overwrite an identical draft."""
    store = FakeTriggerRunStore()
    original = _run(fingerprint="fp-redeliver", parchi_ids=("parchi-for-worker-1",))
    store.claim(original)
    redelivery = _run(fingerprint="fp-redeliver", parchi_ids=("parchi-for-worker-1",))
    claimed = store.claim(redelivery)
    assert claimed is original
    assert claimed.parchi_ids == ("parchi-for-worker-1",)
    assert store.get("fp-redeliver") is original


def test_fingerprint_is_the_declared_dedupe_key() -> None:
    """Two TriggerRuns with the same fingerprint are the same trigger, regardless of how they
    were constructed."""
    a = _run(fingerprint="shared", parchi_ids=("a",))
    b = _run(fingerprint="shared", parchi_ids=("b",))
    store = FakeTriggerRunStore()
    first = store.claim(a)
    second = store.claim(b)
    assert first is second
    assert second.parchi_ids == ("a",)
