"""Closed, immutable expression data. Legal constants and evidence come from the corpus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Predicate:
    operator: str
    evidence: tuple[str, ...]
    field: str | None = None
    value: Any = None
    conditions: tuple[Predicate, ...] = ()

    def walk(self) -> tuple[Predicate, ...]:
        return (self, *(node for child in self.conditions for node in child.walk()))
