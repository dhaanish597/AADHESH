"""Parchi persistence port.

Deliberately narrow. A sealed parchi is append-only evidence, so there is no `update` and no
`delete` on this interface -- the only way to change one is a lifecycle transition in
`aadesh_core.parchi`, which returns a new object for `save` to store.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aadesh_core.parchi import Parchi


@runtime_checkable
class ParchiStore(Protocol):
    def save(self, parchi: Parchi) -> None:
        """Persist a parchi. MUST reject overwriting one that is already SEALED."""
        ...

    def get(self, parchi_id: str) -> Parchi | None: ...

    def for_site(self, site_id: str) -> tuple[Parchi, ...]: ...

    def for_worker(self, worker_id: str) -> tuple[Parchi, ...]: ...
