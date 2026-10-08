"""The six explanation scenarios the layer must support.

Each is an end-to-end pass with a faithful fake model: the request is classified, the model
explains it, and the explanation is grounded and available.
"""

from __future__ import annotations

from aadesh_adapters.explain import FakeExplanationModel
from aadesh_core.authorization import AuthorizationService
from aadesh_core.explanation import ExplanationKind, ExplanationService, ExplanationStatus
from tests.support.authz_builders import FIXED_NOW, parchi_domain, supervisor
from tests.support.explanation_builders import faithful_response, replay_result, resolved_result
from tests.support.stub_authz import StubAuthzProvider


def service() -> ExplanationService:
    return ExplanationService(
        authorization=AuthorizationService(authz=StubAuthzProvider()),
        model=FakeExplanationModel(responder=faithful_response),
    )


def test_obligation_explanation():
    outcome = service().explain_site(
        principal=supervisor(),
        result=resolved_result(stage=3),
        now=FIXED_NOW,
        kind=ExplanationKind.OBLIGATION,
    )
    assert outcome.status is ExplanationStatus.AVAILABLE
    assert outcome.prompt_request.kind is ExplanationKind.OBLIGATION


def test_stage_explanation():
    outcome = service().explain_site(
        principal=supervisor(),
        result=resolved_result(stage=3),
        now=FIXED_NOW,
        kind=ExplanationKind.STAGE,
    )
    assert outcome.status is ExplanationStatus.AVAILABLE


def test_aqi_discrepancy_is_the_default_for_a_divergence():
    outcome = service().explain_site(
        principal=supervisor(),
        result=resolved_result(stage=2, reading_value=420.0, bands=(_band(),)),
        now=FIXED_NOW,
    )
    assert outcome.status is ExplanationStatus.AVAILABLE
    assert outcome.prompt_request.kind is ExplanationKind.AQI_DISCREPANCY
    payload = outcome.prompt_request.to_prompt_payload()
    assert payload["official_stage"] == "Stage II"
    assert payload["implied_stage"] == "Stage III"


def test_historical_replay_explanation():
    outcome = service().explain_site(principal=supervisor(), result=replay_result(), now=FIXED_NOW)
    assert outcome.status is ExplanationStatus.AVAILABLE
    assert outcome.prompt_request.kind is ExplanationKind.HISTORICAL_REPLAY
    assert outcome.prompt_request.mode == "REPLAY"


def test_parchi_pending_acknowledgement_explanation():
    outcome = service().explain_parchi(
        principal=supervisor(), parchi=parchi_domain(), now=FIXED_NOW
    )
    assert outcome.status is ExplanationStatus.AVAILABLE
    assert outcome.prompt_request.kind is ExplanationKind.PARCHI
    assert outcome.prompt_request.parchi_status == "pending_ack"


def test_unknown_fact_explanation():
    outcome = service().explain_site(
        principal=supervisor(),
        result=resolved_result(stage=3, facts={}),
        now=FIXED_NOW,
        kind=ExplanationKind.UNKNOWN_FACT,
    )
    assert outcome.status is ExplanationStatus.AVAILABLE
    assert any(o.status == "unknown" for o in outcome.prompt_request.obligations)


def _band():
    from tests.support.explanation_builders import verified_band

    return verified_band(stage=3)
