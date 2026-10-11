"""Contract tests for the durable consent store.

The same expectations run against both adapters, because the in-memory one and the DynamoDB one
are held to one contract:

  * one record per (worker, facilitator, parchi) scope;
  * scope, expiry and revocation are checked on READ, never assumed from the write;
  * every write is a compare-and-set, and a stale version loses.

The store's whole reason for existing is the last point: a grant formed before a revocation must
not be able to restore the consent afterwards. The tests below reproduce that race rather than
reasoning about it.

The DynamoDB tests run against an in-process double (`tests/support/fake_dynamo.py`). They
exercise the adapter's conditional-write logic; they do NOT prove DynamoDB's own conditional
semantics, which only a real or LocalStack-backed run can. That limitation is reported, not
claimed as coverage.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.memory_consent import InMemoryConsentStore
from aadesh_core.consent import ClaimAssistanceContext, grant_consent, revoke_consent
from aadesh_core.errors import ConsentStoreConflict
from tests.support.fake_dynamo import FakeDynamoResource

GRANTED_AT = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
LIVE_NOW = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)

WORKER = "worker-001"
FACILITATOR = "facilitator-001"
PARCHI = "parchi-001"


def _consent(
    *,
    context_id: str = "ctx-1",
    worker_id: str = WORKER,
    facilitator_id: str = FACILITATOR,
    parchi_id: str = PARCHI,
    granted_at: datetime = GRANTED_AT,
    hours: int = 12,
) -> ClaimAssistanceContext:
    return grant_consent(
        context_id=context_id,
        parchi_id=parchi_id,
        worker_id=worker_id,
        facilitator_id=facilitator_id,
        granted_at=granted_at,
        ttl=timedelta(hours=hours),
        actor_worker_id=worker_id,
    )


def _scope(worker_id: str = WORKER, facilitator_id: str = FACILITATOR, parchi_id: str = PARCHI):
    return {"worker_id": worker_id, "facilitator_id": facilitator_id, "parchi_id": parchi_id}


@pytest.fixture(params=["memory", "dynamo"])
def store(request):
    if request.param == "memory":
        return InMemoryConsentStore()
    from aadesh_adapters.store.dynamo import DynamoConsentStore

    return DynamoConsentStore(dynamo=FakeDynamoResource())


def _live(store, *, now: datetime = LIVE_NOW, **scope):
    return store.find_live(now=now, **_scope(**scope))


# --------------------------------------------------------------------------- basics


def test_a_granted_consent_reads_back_live(store):
    consent = _consent()
    store.save(consent, expected_version=0, actor_id=WORKER)

    found = _live(store)
    assert found is not None
    assert found.context_id == "ctx-1"
    assert found.worker_id == WORKER
    assert found.consent_granted is True


def test_get_by_context_id_returns_the_record(store):
    store.save(_consent(context_id="ctx-handle"), expected_version=0, actor_id=WORKER)
    stored = store.get("ctx-handle")
    assert stored is not None
    assert stored.consent.context_id == "ctx-handle"
    assert stored.version == 1


def test_an_unknown_context_id_is_none(store):
    assert store.get("nope") is None


# --------------------------------------------------------------------------- scope


@pytest.mark.parametrize(
    "scope",
    [
        {"worker_id": "worker-002"},
        {"facilitator_id": "facilitator-002"},
        {"parchi_id": "parchi-002"},
    ],
)
def test_a_consent_does_not_authorize_a_different_scope(store, scope):
    store.save(_consent(), expected_version=0, actor_id=WORKER)
    assert _live(store, **scope) is None


def test_scope_is_part_of_the_key_not_a_filter(store):
    """Two different scopes coexist; neither one authorizes the other's assistance."""
    store.save(
        _consent(context_id="ctx-a", parchi_id="parchi-a"), expected_version=0, actor_id=WORKER
    )
    store.save(
        _consent(context_id="ctx-b", parchi_id="parchi-b"), expected_version=0, actor_id=WORKER
    )
    assert _live(store, parchi_id="parchi-a").context_id == "ctx-a"
    assert _live(store, parchi_id="parchi-b").context_id == "ctx-b"


# --------------------------------------------------------------------------- expiry


def test_an_expired_consent_is_not_live(store):
    expired = _consent(granted_at=LIVE_NOW - timedelta(days=2), hours=1)
    store.save(expired, expected_version=0, actor_id=WORKER)

    # The record still EXISTS -- expiry is a read-time decision, not a deletion.
    assert store.load(**_scope()) is not None
    assert _live(store) is None


def test_expiry_is_checked_against_now_not_a_stored_flag(store):
    store.save(_consent(hours=1), expected_version=0, actor_id=WORKER)
    assert _live(store, now=GRANTED_AT + timedelta(minutes=30)) is not None
    assert _live(store, now=GRANTED_AT + timedelta(hours=2)) is None


# --------------------------------------------------------------------------- revocation


def test_a_revoked_consent_is_not_live_and_keeps_its_history(store):
    store.save(_consent(), expected_version=0, actor_id=WORKER)
    stored = store.load(**_scope())
    revoked = revoke_consent(stored.consent, now=LIVE_NOW)
    store.save(revoked, expected_version=stored.version, actor_id=WORKER)

    assert _live(store) is None
    read_back = store.get("ctx-1")
    assert read_back is not None
    assert read_back.consent.revoked_at is not None
    # The fact that the worker once granted it is preserved, not erased by the revocation.
    assert read_back.consent.consent_granted is True


# --------------------------------------------------------------------------- compare-and-set


def test_a_create_that_collides_with_an_existing_record_is_refused(store):
    store.save(_consent(context_id="ctx-1"), expected_version=0, actor_id=WORKER)
    with pytest.raises(ConsentStoreConflict):
        store.save(_consent(context_id="ctx-2"), expected_version=0, actor_id=WORKER)
    # The refused write changed nothing: the original context still reads live.
    assert _live(store).context_id == "ctx-1"


def test_a_stale_grant_cannot_restore_a_revoked_consent(store):
    """The race this milestone exists for.

    A grant is authorized, the worker revokes, and only then does the grant's write land. The
    write carries the version it read; the record has moved on; it must be refused, and the
    revocation must stand.
    """
    store.save(_consent(context_id="ctx-v1"), expected_version=0, actor_id=WORKER)
    observed = store.load(**_scope())
    assert observed.version == 1

    revoked = revoke_consent(observed.consent, now=LIVE_NOW)
    store.save(revoked, expected_version=observed.version, actor_id=WORKER)

    # The grant that was formed against version 1 now tries to write a live consent.
    stale = _consent(context_id="ctx-stale")
    with pytest.raises(ConsentStoreConflict):
        store.save(stale, expected_version=1, actor_id=WORKER)

    assert _live(store) is None, "a stale write restored a revoked consent"


def test_a_stale_revocation_does_not_overwrite_a_newer_record(store):
    store.save(_consent(context_id="ctx-1"), expected_version=0, actor_id=WORKER)
    first = store.load(**_scope())
    # Somebody else moved the record on (a re-grant superseded it).
    store.save(_consent(context_id="ctx-2"), expected_version=first.version, actor_id=WORKER)

    with pytest.raises(ConsentStoreConflict):
        store.save(
            revoke_consent(first.consent, now=LIVE_NOW),
            expected_version=first.version,
            actor_id=WORKER,
        )
    assert _live(store).context_id == "ctx-2"


def test_concurrent_revocation_and_stale_grant(store) -> None:
    """Run the race for real.

    Two writes carry the SAME expected version -- the revocation and a grant formed before it --
    so exactly one can land. If the revocation lands, the consent is not live; if the grant
    lands, the revocation's write lost and changed nothing. What must never happen is both
    landing, which would be the revocation quietly undone.
    """

    def attempt(snapshot, consent) -> str:
        try:
            store.save(consent, expected_version=snapshot.version, actor_id=WORKER)
            return "won"
        except ConsentStoreConflict:
            return "lost"

    store.save(_consent(context_id="ctx-race"), expected_version=0, actor_id=WORKER)
    snapshot = store.load(**_scope())
    revoked = revoke_consent(snapshot.consent, now=LIVE_NOW)
    regrant = _consent(context_id="ctx-raced")

    with ThreadPoolExecutor(max_workers=2) as pool:
        revoke_future = pool.submit(attempt, snapshot, revoked)
        grant_future = pool.submit(attempt, snapshot, regrant)
        results = [revoke_future.result(), grant_future.result()]

    assert results.count("won") == 1, "both writes carried the same version and both landed"
    final = store.load(**_scope())
    if final.consent.revoked_at is not None:
        assert _live(store) is None
    else:
        assert final.consent.context_id == "ctx-raced"


# --------------------------------------------------------------------------- DynamoDB-only


def test_dynamo_sets_a_ttl_but_does_not_use_it_as_the_check():
    """TTL is housekeeping, not authorization.

    The item carries a `ttl`, and DynamoDB will delete it days later. The authorization check
    must ignore that entirely: it compares `expires_at` against `now`, so a record past its
    window is denied while it still exists.
    """
    from aadesh_adapters.store.dynamo import DynamoConsentStore

    resource = FakeDynamoResource()
    store = DynamoConsentStore(dynamo=resource)
    store.save(_consent(hours=1), expected_version=0, actor_id=WORKER)

    item = resource.Table("aadesh-consents").items["consent#worker-001#facilitator-001#parchi-001"]
    assert item["ttl"] == int(GRANTED_AT.timestamp()) + 3600
    # The item is still present, and still denied, one hour after it lapsed.
    assert _live(store, now=GRANTED_AT + timedelta(hours=2)) is None


def test_dynamo_ignores_a_malformed_stored_record():
    from aadesh_adapters.store.dynamo import DynamoConsentStore

    resource = FakeDynamoResource()
    store = DynamoConsentStore(dynamo=resource)
    table = resource.Table("aadesh-consents")
    table.items["consent#worker-001#facilitator-001#parchi-001"] = {
        "scope_key": "consent#worker-001#facilitator-001#parchi-001",
        "kind": "consent",
        "context_id": "ctx-bad",
        "version": 1,
        "record": "{}",  # not a ClaimAssistanceContext
    }
    # A record that cannot be reconstructed is not consent: it reads as absent, so the caller
    # denies rather than building a view from something it only half-understands.
    assert _live(store) is None
    assert store.get("ctx-bad") is None
