"""INVARIANT: the service presents a model explanation only when it is grounded, and otherwise
shows the deterministic text -- while the deterministic result itself is untouched.

The model is an optional coat of paint. Every failure mode below ends in the same place: the
deterministic sentence the engine produced, with an explicit status.
"""

from __future__ import annotations

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.explain import FakeExplanationModel
from aadesh_core.authorization import AuthorizationService
from aadesh_core.explanation import (
    AUDIT_EVENT,
    ExplanationService,
    ExplanationStatus,
    explain_set,
)
from tests.support.authz_builders import FIXED_NOW, supervisor
from tests.support.explanation_builders import faithful_response, resolved_result
from tests.support.stub_authz import StubAuthzProvider


def service(model) -> ExplanationService:
    return ExplanationService(
        authorization=AuthorizationService(authz=StubAuthzProvider()), model=model
    )


def test_a_grounded_explanation_is_available():
    model = FakeExplanationModel(responder=faithful_response)
    result = resolved_result(stage=3)
    outcome = service(model).explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    assert outcome.status is ExplanationStatus.AVAILABLE
    assert outcome.explanation.source == "model"
    assert outcome.deterministic.source == "deterministic"


def test_no_model_returns_explanation_unavailable_but_deterministic_text():
    result = resolved_result(stage=3)
    outcome = service(None).explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    assert outcome.status is ExplanationStatus.EXPLANATION_UNAVAILABLE
    assert outcome.explanation.source == "deterministic"
    assert outcome.deterministic == explain_set(result)


def test_a_model_error_returns_explanation_unavailable():
    model = FakeExplanationModel(error=RuntimeError("bedrock outage"))
    result = resolved_result(stage=3)
    outcome = service(model).explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    assert outcome.status is ExplanationStatus.EXPLANATION_UNAVAILABLE
    assert outcome.explanation.source == "deterministic"


def test_malformed_structured_output_returns_explanation_unavailable():
    model = FakeExplanationModel(malformed=True)
    result = resolved_result(stage=3)
    outcome = service(model).explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    assert outcome.status is ExplanationStatus.EXPLANATION_UNAVAILABLE


def test_a_hallucinated_citation_is_unsupported_and_deterministic_is_shown():
    def hallucinate(request):
        return faithful_response(
            request, source_references=[{"source_doc": "invented-order", "page": 3}]
        )

    result = resolved_result(stage=3)
    outcome = service(FakeExplanationModel(responder=hallucinate)).explain_site(
        principal=supervisor(), result=result, now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert outcome.explanation.source == "deterministic"
    assert any(u.kind == "unknown-citation" for u in outcome.unsupported)


def test_a_contradicted_obligation_status_is_unsupported():
    result = resolved_result(stage=3, facts={})  # obligation is UNKNOWN

    def upgrade(request):
        return faithful_response(
            request,
            claims=[{"clause_id": o.obligation_id, "status": "met"} for o in request.obligations],
        )

    outcome = service(FakeExplanationModel(responder=upgrade)).explain_site(
        principal=supervisor(), result=result, now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert any(v.kind == "contradicts-engine" for v in outcome.violations)


def test_the_audit_record_has_no_prose_and_carries_the_outcome():
    audit = RecordingAuditLog()
    model = FakeExplanationModel(responder=faithful_response)
    result = resolved_result(stage=3)
    service_with_audit = ExplanationService(
        authorization=AuthorizationService(authz=StubAuthzProvider()),
        model=model,
        audit=audit,
    )
    service_with_audit.explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    records = audit.for_event(AUDIT_EVENT)
    assert len(records) == 1
    detail = records[0].detail
    assert detail["outcome"] == "AVAILABLE"
    assert "explanation_id" in detail
    assert records[0].as_text().count("This site has") == 0
