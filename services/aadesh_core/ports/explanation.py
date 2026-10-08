"""Explanation port. Outside the enforcement path, and optional by construction.

An implementation may fail, time out, or be absent entirely. Callers go through
`aadesh_core.explanation.explain_with_fallback`, which validates output against the contract
and substitutes deterministic text on any problem. Nothing downstream is allowed to depend
on this port succeeding.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aadesh_core.explanation import Explanation, ExplanationContext


@runtime_checkable
class ExplanationProvider(Protocol):
    def explain(self, *, prompt: str, context: ExplanationContext) -> Explanation | None:
        """Render already-computed results into prose. MUST NOT compute anything new."""
        ...
