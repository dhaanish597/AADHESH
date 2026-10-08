"""Explanation port. Outside the enforcement path, and optional by construction.

An implementation may fail, time out, or be absent entirely. Callers go through
`aadesh_core.explanation.ExplanationService`, which validates output against the contract and
grounding checks and substitutes deterministic text on any problem. Nothing downstream is
allowed to depend on this port succeeding.

Two protocols live here. `ExplanationProvider` is the original free-prose contract.
`ExplanationModel` is the structured one Prompt 9's Bedrock and Strands adapters satisfy: it
receives an `ExplanationRequest` (only the facts the engine computed) and returns an
`ExplanationResponse` or None. Implementations MUST NOT compute anything new, MUST NOT mutate
any decision, and MUST NOT be given tools that could act on the compliance system.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aadesh_core.explanation import (
    Explanation,
    ExplanationContext,
    ExplanationRequest,
    ExplanationResponse,
)


@runtime_checkable
class ExplanationProvider(Protocol):
    def explain(self, *, prompt: str, context: ExplanationContext) -> Explanation | None:
        """Render already-computed results into prose. MUST NOT compute anything new."""
        ...


@runtime_checkable
class ExplanationModel(Protocol):
    def explain(self, *, request: ExplanationRequest) -> ExplanationResponse | None:
        """Explain an already-computed result from a structured request.

        Returns a structured response, or None when no explanation could be produced. The
        caller is responsible for grounding and contract-checking whatever comes back; an
        implementation MUST NOT apply it to any state.
        """
        ...
