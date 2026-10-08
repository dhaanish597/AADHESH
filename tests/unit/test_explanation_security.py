"""The security properties the explanation layer must hold.

Each test corresponds to one claim: the model cannot reach a decision, and the AI layer cannot
be used to reach past a boundary. Where a behaviour is structural rather than behavioural (the
service simply has no way to authorize or acknowledge), the test asserts the structure, because
that is the property being relied on.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from aadesh_adapters.explain import FakeExplanationModel
from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import VIEW_PARCHI
from aadesh_core.errors import AuthorizationDenied
from aadesh_core.explanation import (
    ExplanationService,
    ExplanationStatus,
    explain_set,
    request_for_parchi,
)
from tests.support.authz_builders import FIXED_NOW, facilitator, parchi_domain, supervisor
from tests.support.explanation_builders import faithful_response, replay_result, resolved_result
from tests.support.stub_authz import StubAuthzProvider


def service_with(responder, *, deny_actions=frozenset()):
    model = FakeExplanationModel(responder=responder)
    service = ExplanationService(
        authorization=AuthorizationService(
            authz=StubAuthzProvider(deny_actions=frozenset(deny_actions))
        ),
        model=model,
    )
    return service, model


def test_1_llm_cannot_change_the_deterministic_result():
    result = resolved_result(stage=3)
    service, _ = service_with(faithful_response)
    outcome = service.explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    assert outcome.deterministic == explain_set(result)
    assert outcome.prompt_request.official_stage == "Stage III"
    assert result.stage_status.official_stage == 3


def test_2_llm_cannot_activate_a_stage():
    result = resolved_result(stage=2)

    def overreach(request):
        return faithful_response(request, official_stage="Stage IV")

    outcome = service_with(overreach)[0].explain_site(
        principal=supervisor(), result=result, now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert outcome.prompt_request.official_stage == "Stage II"


def test_3_llm_cannot_create_an_obligation():
    result = resolved_result(stage=3)

    def invent(request):
        return faithful_response(
            request, claims=[{"clause_id": "grap9-invented-clause", "status": "not_met"}]
        )

    outcome = service_with(invent)[0].explain_site(
        principal=supervisor(), result=result, now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert any(v.kind == "unknown-clause" for v in outcome.violations)


def test_4_llm_cannot_authorize_a_user():
    # Structural: the service exposes no authorization operation, and a denied principal never
    # reaches the model whatever it returns.
    service, model = service_with(faithful_response, deny_actions={"ViewSiteExecution"})
    assert not hasattr(service, "authorize")
    with pytest.raises(AuthorizationDenied):
        service.explain_site(principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW)
    assert model.calls == []


def test_5_llm_cannot_acknowledge_a_parchi():
    service, model = service_with(faithful_response)
    parchi = parchi_domain()
    service.explain_parchi(principal=supervisor(), parchi=parchi, now=FIXED_NOW)
    assert not hasattr(service, "acknowledge")
    assert parchi.state.value == "pending_ack"  # unchanged by any model output
    assert len(model.calls) == 1


def test_6_llm_cannot_seal_a_parchi():
    service, _ = service_with(faithful_response)
    assert not hasattr(service, "seal")
    parchi = parchi_domain()
    service.explain_parchi(principal=supervisor(), parchi=parchi, now=FIXED_NOW)
    assert parchi.content_hash is None


def test_7_llm_cannot_modify_source_data():
    # Deterministic resolution is a pure function: explaining it cannot change the next result.
    before = resolved_result(stage=3)
    service, _ = service_with(faithful_response)
    service.explain_site(principal=supervisor(), result=before, now=FIXED_NOW)
    after = resolved_result(stage=3)
    assert before == after
    assert before.stage_status.official_stage == after.stage_status.official_stage


def test_8_hallucinated_citations_are_rejected():
    def hallucinate(request):
        return faithful_response(
            request, source_references=[{"source_doc": "fake-order", "page": 1}]
        )

    outcome = service_with(hallucinate)[0].explain_site(
        principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert any(u.kind == "unknown-citation" for u in outcome.unsupported)


def test_9_hallucinated_monetary_amounts_are_rejected():
    def invent_amount(request):
        return faithful_response(request, summary="You will receive \u20b98,000 in compensation.")

    outcome = service_with(invent_amount)[0].explain_site(
        principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert outcome.deterministic.source == "deterministic"


def test_10_historical_replay_remains_historical():
    def relabel(request):
        return faithful_response(request, replay_status="CURRENT")

    outcome = service_with(relabel)[0].explain_site(
        principal=supervisor(), result=replay_result(), now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert outcome.prompt_request.mode == "REPLAY"


def test_11_unknown_remains_unknown():
    result = resolved_result(stage=3, facts={})

    def upgrade(request):
        return faithful_response(
            request,
            claims=[{"clause_id": o.obligation_id, "status": "met"} for o in request.obligations],
        )

    outcome = service_with(upgrade)[0].explain_site(
        principal=supervisor(), result=result, now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.UNSUPPORTED
    assert any(v.kind == "contradicts-engine" for v in outcome.violations)


def test_12_bedrock_outage_does_not_affect_the_deterministic_workflow():
    result = resolved_result(stage=3)
    model = FakeExplanationModel(error=RuntimeError("bedrock unreachable"))
    service = ExplanationService(
        authorization=AuthorizationService(authz=StubAuthzProvider()), model=model
    )
    outcome = service.explain_site(principal=supervisor(), result=result, now=FIXED_NOW)
    assert outcome.status is ExplanationStatus.EXPLANATION_UNAVAILABLE
    assert outcome.explanation == explain_set(result)
    # The deterministic result is untouched and reproducible with the model down.
    assert result == resolved_result(stage=3)


def test_13_unauthorized_user_cannot_obtain_protected_context():
    service, model = service_with(faithful_response, deny_actions={"ViewSiteExecution"})
    with pytest.raises(AuthorizationDenied):
        service.explain_site(principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW)
    assert model.calls == []


def test_14_facilitator_cannot_bypass_view_parchi():
    service, model = service_with(faithful_response, deny_actions={VIEW_PARCHI})
    with pytest.raises(AuthorizationDenied):
        service.explain_parchi(principal=facilitator(), parchi=parchi_domain(), now=FIXED_NOW)
    assert model.calls == []


def test_15_raw_qr_token_is_never_sent_to_the_model():
    parchi = replace(
        parchi_domain(), acknowledgement_token_ref="sha256-derived-reference-not-a-token"
    )
    request = request_for_parchi(parchi)
    payload = json.dumps(request.to_prompt_payload())
    assert "aadesh://ack/" not in payload
    assert "sha256-derived-reference-not-a-token" not in payload
    assert "token" not in payload.lower()
