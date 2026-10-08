"""Explanation layer. Strictly outside the enforcement path.

Contract and deterministic text are the fallback that always exists. Context/response/prompt
define the structured input and output of the optional model. Grounding refuses anything the
model was not given. `service.ExplanationService` ties them together behind authorization.

The import order below matters for one reason: `service` imports `grounding`, which imports
`response`, so all three are loaded by the time this module finishes. Nothing here imports an
adapter; the dependency direction is adapters -> core.
"""

from __future__ import annotations

from aadesh_core.explanation.context import (
    DEFAULT_DISCLAIMER,
    SCHEMA_VERSION,
    ExplanationCitation,
    ExplanationFact,
    ExplanationKind,
    ExplanationObligation,
    ExplanationRequest,
    request_for_parchi,
    request_for_resolution,
)
from aadesh_core.explanation.contract import (
    BANNED_PHRASES,
    ContractViolation,
    Explanation,
    ExplanationClaim,
    ExplanationContext,
    check_explanation,
    check_prose,
    explain_with_fallback,
)
from aadesh_core.explanation.deterministic import context_for, explain_result, explain_set
from aadesh_core.explanation.grounding import UnsupportedReference, check_grounding
from aadesh_core.explanation.prompt import SYSTEM_PROMPT, build_prompt
from aadesh_core.explanation.response import ExplanationResponse, SourceReference
from aadesh_core.explanation.service import (
    AUDIT_EVENT,
    ExplanationOutcome,
    ExplanationService,
    ExplanationStatus,
)

__all__ = [
    "AUDIT_EVENT",
    "BANNED_PHRASES",
    "DEFAULT_DISCLAIMER",
    "SCHEMA_VERSION",
    "SYSTEM_PROMPT",
    "ContractViolation",
    "Explanation",
    "ExplanationCitation",
    "ExplanationClaim",
    "ExplanationContext",
    "ExplanationFact",
    "ExplanationKind",
    "ExplanationObligation",
    "ExplanationOutcome",
    "ExplanationRequest",
    "ExplanationResponse",
    "ExplanationService",
    "ExplanationStatus",
    "SourceReference",
    "UnsupportedReference",
    "build_prompt",
    "check_explanation",
    "check_grounding",
    "check_prose",
    "context_for",
    "explain_result",
    "explain_set",
    "explain_with_fallback",
    "request_for_parchi",
    "request_for_resolution",
]
