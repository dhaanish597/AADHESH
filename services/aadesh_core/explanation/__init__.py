"""Explanation layer. Strictly outside the enforcement path."""

from __future__ import annotations

from aadesh_core.explanation.contract import (
    BANNED_PHRASES,
    ContractViolation,
    Explanation,
    ExplanationClaim,
    ExplanationContext,
    check_explanation,
    explain_with_fallback,
)
from aadesh_core.explanation.deterministic import context_for, explain_result, explain_set

__all__ = [
    "BANNED_PHRASES",
    "ContractViolation",
    "Explanation",
    "ExplanationClaim",
    "ExplanationContext",
    "check_explanation",
    "context_for",
    "explain_result",
    "explain_set",
    "explain_with_fallback",
]
