"""In-memory parchi store. The default for tests and local development.

Held to the same contract as the DynamoDB adapter, including the refusal to overwrite a
sealed parchi.
"""

from __future__ import annotations

from aadesh_core.domain import ParchiState
from aadesh_core.errors import IllegalParchiTransition
from aadesh_core.parchi import Parchi


class InMemoryParchiStore:
    def __init__(self) -> None:
        self._items: dict[str, Parchi] = {}

    def save(self, parchi: Parchi) -> None:
        existing = self._items.get(parchi.parchi_id)
        if existing is not None and existing.state is ParchiState.SEALED:
            raise IllegalParchiTransition(
                f"Parchi {parchi.parchi_id} is sealed and cannot be overwritten. "
                f"Sealed records are append-only evidence."
            )
        self._items[parchi.parchi_id] = parchi

    def get(self, parchi_id: str) -> Parchi | None:
        return self._items.get(parchi_id)

    def for_site(self, site_id: str) -> tuple[Parchi, ...]:
        return tuple(p for p in self._items.values() if p.site_id == site_id)

    def for_worker(self, worker_id: str) -> tuple[Parchi, ...]:
        return tuple(p for p in self._items.values() if p.worker_id == worker_id)
