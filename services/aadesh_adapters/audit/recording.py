"""An audit sink that keeps what it is told, for tests and local runs.

Exists so a test can assert what was actually written to the audit trail -- specifically,
that the raw acknowledgement token is not in it. `StdoutAuditLog` is the adapter for looking
at; this is the adapter for checking.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event: str
    detail: Mapping[str, Any]

    def as_text(self) -> str:
        """Every key and value flattened into one string.

        The privacy tests search this rather than individual fields, so a value smuggled into
        a nested structure or a key name is still found.
        """
        parts: list[str] = [self.event]
        for key, value in self.detail.items():
            parts.append(str(key))
            parts.append(str(value))
        return " ".join(parts)


class RecordingAuditLog:
    """Holds every recorded event, in order."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, *, event: str, detail: Mapping[str, Any]) -> None:
        self.records.append(AuditRecord(event=event, detail=dict(detail)))

    def for_event(self, event: str) -> tuple[AuditRecord, ...]:
        return tuple(r for r in self.records if r.event == event)

    def all_text(self) -> str:
        return "\n".join(r.as_text() for r in self.records)
