"""The token that lets a worker's acknowledgement resume a waiting execution.

Stored on receive, removed on read. Delete-on-read is what makes a retried resume a no-op
instead of a second SendTaskSuccess.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.memory_task_token import InMemoryTaskTokenStore
from aadesh_core.ports.task_token import TaskTokenStore

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
def store() -> InMemoryTaskTokenStore:
    return InMemoryTaskTokenStore()


def test_satisfies_the_port(store) -> None:
    assert isinstance(store, TaskTokenStore)


def test_pop_returns_the_token_once(store) -> None:
    store.put(parchi_id="parchi-001", task_token="tok-abc", expires_at=NOW + timedelta(hours=24))
    assert store.pop(parchi_id="parchi-001") == "tok-abc"
    assert store.pop(parchi_id="parchi-001") is None, "a second pop must not yield the token again"


def test_peek_does_not_remove(store) -> None:
    store.put(parchi_id="parchi-001", task_token="tok-abc", expires_at=NOW + timedelta(hours=24))
    assert store.peek(parchi_id="parchi-001") == "tok-abc"
    assert store.peek(parchi_id="parchi-001") == "tok-abc"


def test_unknown_parchi_returns_none_rather_than_raising(store) -> None:
    assert store.pop(parchi_id="nope") is None


def test_naive_expiry_is_refused(store) -> None:
    """A naive expiry compared against timezone-aware Lambda clock reads expires early or
    late depending on the host. Refuse it at the door."""
    with pytest.raises(ValueError, match="timezone-aware"):
        store.put(
            parchi_id="parchi-001",
            task_token="tok-abc",
            expires_at=datetime(2026, 10, 10, 9, 0),
        )
