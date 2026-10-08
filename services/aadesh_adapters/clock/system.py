"""Clock adapters."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Wall clock, always timezone-aware."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """A clock that does not move. For tests and for reproducible replays."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._at = at

    def now(self) -> datetime:
        return self._at
