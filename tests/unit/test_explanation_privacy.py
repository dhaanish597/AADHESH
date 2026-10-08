"""INVARIANT: the explanation layer never carries worker personal data to the model.

The AI layer must not become a second way to read a Parchi. The request carries opaque
references and compliance facts only; the audit record carries no prompt and no prose.
"""

from __future__ import annotations

import json

import pytest

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.explain import FakeExplanationModel
from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import VIEW_PARCHI
from aadesh_core.errors import AuthorizationDenied
from aadesh_core.explanation import ExplanationService, build_prompt, request_for_parchi
from tests.support.authz_builders import FIXED_NOW, facilitator, parchi_domain, supervisor
from tests.support.explanation_builders import faithful_response, resolved_result
from tests.support.stub_authz import StubAuthzProvider

BANNED_TERMS = [
    "aadhaar",
    "aadhar",
    "phone",
    "mobile",
    "whatsapp",
    "bank",
    "ifsc",
    "upi",
    "pan",
    "address",
    "salary",
    "wage",
    "aadesh://ack/",
]


def _assert_clean(text: str) -> None:
    lowered = text.lower()
    for term in BANNED_TERMS:
        assert term not in lowered, f"explanation context leaked {term!r}"


def test_a_site_explanation_payload_carries_no_personal_data():
    from aadesh_core.explanation import request_for_resolution

    request = request_for_resolution(resolved_result(stage=3))
    _assert_clean(json.dumps(request.to_prompt_payload()))


def test_a_parchi_explanation_payload_omits_worker_identity():
    parchi = parchi_domain(worker_id="wrk-should-not-appear")
    request = request_for_parchi(parchi)
    payload = json.dumps(request.to_prompt_payload())
    assert "wrk-should-not-appear" not in payload
    _assert_clean(payload)


def test_the_model_prompt_contains_no_personal_data():
    request = request_for_parchi(parchi_domain(worker_id="wrk-should-not-appear"))
    _assert_clean(build_prompt(request))


def test_the_audit_record_contains_no_prompt_or_prose():
    audit = RecordingAuditLog()
    service = ExplanationService(
        authorization=AuthorizationService(authz=StubAuthzProvider()),
        model=FakeExplanationModel(responder=faithful_response),
        audit=audit,
    )
    service.explain_site(principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW)
    _assert_clean(audit.all_text())


def test_a_facilitator_denied_view_parchi_gets_no_explanation_context():
    model = FakeExplanationModel(responder=faithful_response)
    service = ExplanationService(
        authorization=AuthorizationService(
            authz=StubAuthzProvider(deny_actions=frozenset({VIEW_PARCHI}))
        ),
        model=model,
    )
    with pytest.raises(AuthorizationDenied):
        service.explain_parchi(
            principal=facilitator(), parchi=parchi_domain(worker_id="wrk-1"), now=FIXED_NOW
        )
    assert model.calls == []
