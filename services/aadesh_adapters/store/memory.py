"""In-memory parchi store. The default for tests and local development.

Held to the same contract as the DynamoDB adapter, including the refusal to overwrite a
sealed parchi and the atomic conditional create behind `save_new`.

The lock is here because two of the operations this store supports are only correct if they
are indivisible: refusing to overwrite a sealed record, and refusing a duplicate idempotency
key. Neither is a property of a single dict assignment, so "the GIL makes it atomic" is not
an argument that survives a different interpreter or a different adapter.
"""

from __future__ import annotations

import threading

from aadesh_core.domain import ParchiState
from aadesh_core.errors import DuplicateIdempotencyKey, IllegalParchiTransition
from aadesh_core.parchi import Parchi


class InMemoryParchiStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, Parchi] = {}

    def save(self, parchi: Parchi) -> None:
        with self._lock:
            existing = self._items.get(parchi.parchi_id)
            if existing is not None and existing.state is ParchiState.SEALED:
                raise IllegalParchiTransition(
                    f"Parchi {parchi.parchi_id} is sealed and cannot be overwritten. "
                    f"Sealed records are append-only evidence."
                )
            self._items[parchi.parchi_id] = parchi

    def save_new(self, parchi: Parchi) -> None:
        """Conditional create. Raises `DuplicateIdempotencyKey` if the key is already taken.

        The lookup and the write share one lock, so the two callers racing on a key are
        separated here rather than by luck.
        """
        key = parchi.idempotency_key
        with self._lock:
            if key is not None and any(p.idempotency_key == key for p in self._items.values()):
                raise DuplicateIdempotencyKey(key)
            self._items[parchi.parchi_id] = parchi

    def get(self, parchi_id: str) -> Parchi | None:
        with self._lock:
            return self._items.get(parchi_id)

    def for_site(self, site_id: str) -> tuple[Parchi, ...]:
        with self._lock:
            return tuple(p for p in self._items.values() if p.site_id == site_id)

    def for_worker(self, worker_id: str) -> tuple[Parchi, ...]:
        with self._lock:
            return tuple(p for p in self._items.values() if p.worker_id == worker_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> Parchi | None:
        """The parchi created under this key, or None.

        A production adapter needs a real index or a conditional write here; a linear scan is
        fine in memory and honest about it.
        """
        with self._lock:
            return next(
                (p for p in self._items.values() if p.idempotency_key == idempotency_key),
                None,
            )
