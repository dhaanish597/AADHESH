"""Clock port. Time is injected, never read from inside the domain.

A resolver that reads the clock is not a pure function and cannot be tested for determinism.
Every timestamp that ends up on a parchi comes through here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current time. MUST be timezone-aware."""
        ...
