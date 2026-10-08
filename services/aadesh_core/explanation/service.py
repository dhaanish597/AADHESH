"""The explanation service: authorize, render, check, fall back -- in that order.

This is the one module a handler calls. It does four things, and the order is the design:

  1. **Authorize.** The caller may only receive explanation context they are already entitled
     to see. A site explanation requires `ViewSiteExecution` on that site; a Parchi
     explanation requires `ViewParchi` on that Parchi. A facilitator denied `ViewParchi` gets
     an authorization error here, BEFORE any protected data is gathered and before the model
     is called. The AI layer is not a backdoor around Cedar.

  2. **Render.** The deterministic result is turned into an `ExplanationRequest` and the model
     is asked to explain it. The authoritative `ResolutionResult` / `Parchi` is kept by the
     caller and is never replaced by the model's output.

  3. **Check.** The response is grounded against the request (`grounding.check_grounding`) and
     held to the output contract (`contract.check_explanation`). A response that contradicts
     the engine, invents a citation or changes a stage is marked UNSUPPORTED.

  4. **Fall back.** On an unavailable model, a malformed response, or any violation, the
     deterministic text is shown and the outcome carries `EXPLANATION_UNAVAILABLE` or
     `UNSUPPORTED`. Compliance resolution is never affected: this service does not touch an
     obligation, a stage, an authorization decision, or a Parchi state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from aadesh_core.domain import ParchiState, Principal, ResolutionResult
from aadesh_core.domain.models import stage_name
from aadesh_core.explanation.context import (
    ExplanationFact,
    ExplanationKind,
    ExplanationRequest,
    request_for_parchi,
    request_for_resolution,
)
from aadesh_core.explanation.contract import (
    ContractViolation,
    Explanation,
    check_explanation,
    check_prose,
)
from aadesh_core.explanation.deterministic import explain_set
from aadesh_core.explanation.grounding import UnsupportedReference, check_grounding
from aadesh_core.explanation.response import ExplanationResponse
from aadesh_core.parchi import Parchi

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps the core free of the adapters
    from aadesh_core.authorization.service import AuthorizationService
    from aadesh_core.ports.audit import AuditLog
    from aadesh_core.ports.explanation import ExplanationModel

AUDIT_EVENT = "ExplanationRequested"

_PARCHI_SENTENCE = {
    ParchiState.DRAFT: "This Parchi is a draft and has not yet been issued to the worker.",
    ParchiState.PENDING_ACK: (
        "This Parchi is pending acknowledgement: it has been issued and is waiting for the "
        "named worker to confirm it personally."
    ),
    ParchiState.ACKNOWLEDGED: (
        "The named worker has acknowledged this Parchi. It is not yet sealed, so the record "
        "is not frozen."
    ),
    ParchiState.SEALED: (
        "This Parchi is sealed. The record is frozen over a content hash and cannot change."
    ),
    ParchiState.VOID: "This Parchi was cancelled before sealing and is no longer active.",
}


class ExplanationStatus(StrEnum):
    """The outcome of the explanation layer. Never the outcome of the compliance decision."""

    AVAILABLE = "AVAILABLE"
    """A grounded, contract-compliant model explanation is shown."""

    UNSUPPORTED = "UNSUPPORTED"
    """The model went beyond its context or breached the contract. Deterministic text is shown."""

    EXPLANATION_UNAVAILABLE = "EXPLANATION_UNAVAILABLE"
    """No usable explanation could be produced. Deterministic text is shown. Aadesh still works."""


@dataclass(frozen=True, slots=True)
class ExplanationOutcome:
    """What a caller gets. `request` and `deterministic` are the authoritative, unchanged result;
    `explanation` is the presentation the user may read."""

    prompt_request: ExplanationRequest
    status: ExplanationStatus
    deterministic: Explanation
    explanation: Explanation
    violations: tuple[ContractViolation, ...] = ()
    unsupported: tuple[UnsupportedReference, ...] = ()
    model_metadata: Mapping[str, str] = field(default_factory=dict)
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "violations", tuple(self.violations))
        object.__setattr__(self, "unsupported", tuple(self.unsupported))
        object.__setattr__(self, "model_metadata", MappingProxyType(dict(self.model_metadata)))

    @property
    def explanation_id(self) -> str:
        return self.prompt_request.context_id

    @property
    def is_available(self) -> bool:
        return self.status is ExplanationStatus.AVAILABLE


class ExplanationService:
    """Authorize, then explain. Construct with the model and audit sink for the environment."""

    def __init__(
        self,
        *,
        authorization: AuthorizationService,
        model: ExplanationModel | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._authorization = authorization
        self._model = model
        self._audit = audit

    # -- site explanations -------------------------------------------------------

    def explain_site(
        self,
        *,
        principal: Principal,
        result: ResolutionResult,
        now: datetime,
        kind: ExplanationKind | None = None,
        question: str | None = None,
        facts: Iterable[ExplanationFact] = (),
        explanation_id: str | None = None,
    ) -> ExplanationOutcome:
        """Explain a resolved obligation set, if `principal` may view this site's execution."""
        self._authorization.require_view_site_execution(
            principal=principal, site_id=result.site_id, now=now
        )
        request = request_for_resolution(
            result, kind=kind, question=question, facts=facts, context_id=explanation_id
        )
        return self._render(request, deterministic=explain_set(result))

    # -- parchi explanations -----------------------------------------------------

    def explain_parchi(
        self,
        *,
        principal: Principal,
        parchi: Parchi,
        now: datetime,
        question: str | None = None,
        explanation_id: str | None = None,
    ) -> ExplanationOutcome:
        """Explain a Parchi's lifecycle state, if `principal` may view this Parchi.

        A facilitator who may only `AssistClaim` is refused here: the same `ViewParchi` decision
        that guards the record guards its explanation. No model is called on refusal.
        """
        self._authorization.require_view_parchi(principal=principal, parchi=parchi, now=now)
        request = request_for_parchi(parchi, question=question, context_id=explanation_id)
        return self._render(request, deterministic=_deterministic_parchi(parchi))

    # -- internals ---------------------------------------------------------------

    def _render(
        self, request: ExplanationRequest, *, deterministic: Explanation
    ) -> ExplanationOutcome:
        if self._model is None:
            return self._unavailable(request, deterministic, detail="no explanation model")

        try:
            response = self._model.explain(request=request)
        except Exception as exc:
            detail = f"model error: {type(exc).__name__}"
            self._record(request, ExplanationStatus.EXPLANATION_UNAVAILABLE, detail)
            return self._unavailable(request, deterministic, detail=detail)

        if response is None:
            self._record(
                request, ExplanationStatus.EXPLANATION_UNAVAILABLE, "model returned no output"
            )
            return self._unavailable(request, deterministic, detail="model returned no output")

        violations, unsupported = self._check(response, request)
        if violations or unsupported:
            self._record(request, ExplanationStatus.UNSUPPORTED, "rejected by contract/grounding")
            return ExplanationOutcome(
                prompt_request=request,
                status=ExplanationStatus.UNSUPPORTED,
                deterministic=deterministic,
                explanation=deterministic,
                violations=tuple(violations),
                unsupported=tuple(unsupported),
                detail="model output rejected; deterministic text shown",
            )

        model_explanation = Explanation(text=response.text, claims=response.claims, source="model")
        self._record(request, ExplanationStatus.AVAILABLE, None)
        return ExplanationOutcome(
            prompt_request=request,
            status=ExplanationStatus.AVAILABLE,
            deterministic=deterministic,
            explanation=model_explanation,
            model_metadata=response.model_metadata,
        )

    def _check(
        self, response: ExplanationResponse, request: ExplanationRequest
    ) -> tuple[list[ContractViolation], list[UnsupportedReference]]:
        unsupported = list(check_grounding(response, request=request))
        if request.obligations:
            candidate = Explanation(text=response.text, claims=response.claims, source="model")
            violations = list(check_explanation(candidate, context=request.contract_context()))
        else:
            violations = list(check_prose(response.text, has_cited_amount=request.has_cited_amount))
        return violations, unsupported

    def _unavailable(
        self, request: ExplanationRequest, deterministic: Explanation, *, detail: str
    ) -> ExplanationOutcome:
        return ExplanationOutcome(
            prompt_request=request,
            status=ExplanationStatus.EXPLANATION_UNAVAILABLE,
            deterministic=deterministic,
            explanation=deterministic,
            detail=detail,
        )

    def _record(
        self, request: ExplanationRequest, status: ExplanationStatus, detail: str | None
    ) -> None:
        """Record an audit line. Opaque references only: no prompt, no prose, no personal data."""
        if self._audit is None:
            return
        record: dict[str, object] = {
            "explanation_id": request.context_id,
            "kind": request.kind.value,
            "site_ref": request.site_ref,
            "parchi_ref": request.parchi_ref,
            "model": type(self._model).__name__ if self._model is not None else "none",
            "outcome": status.value,
        }
        if detail is not None:
            record["detail"] = detail
        self._audit.record(event=AUDIT_EVENT, detail=record)


def _deterministic_parchi(parchi: Parchi) -> Explanation:
    """The always-available Parchi explanation. No model, no network."""
    lines = [_PARCHI_SENTENCE[parchi.state]]
    if parchi.stage is not None:
        lines.append(
            f"It rests on the verified official invocation of {stage_name(parchi.stage.stage)} "
            f"(order {parchi.stage.order_doc_id})."
        )
    else:
        lines.append("It is not tied to a current verified official GRAP invocation.")
    if parchi.provenance is not None and not parchi.cites_measured_data:
        lines.append(f"The reading behind it is {parchi.provenance.value}, not a live measurement.")
    return Explanation(text=" ".join(lines), claims=(), source="deterministic")


__all__ = ["AUDIT_EVENT", "ExplanationOutcome", "ExplanationService", "ExplanationStatus"]
