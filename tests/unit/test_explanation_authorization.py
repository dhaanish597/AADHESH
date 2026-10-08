"""INVARIANT: the AI layer is not a backdoor around Cedar.

An explanation is only built for a principal who is already authorized to see the underlying
data. On a denial the model is NEVER called -- no protected context is gathered, so there is
nothing for a prompt or a provider to leak. The facilitator case is the important one: a
facilitator who may `AssistClaim` but may not `ViewParchi` gets the same refusal the record
itself gives.
"""

from __future__ import annotations

import pytest

from aadesh_adapters.explain import FakeExplanationModel
from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import VIEW_PARCHI, VIEW_SITE_EXECUTION
from aadesh_core.errors import AuthorizationDenied
from aadesh_core.explanation import ExplanationService
from tests.support.authz_builders import (
    FIXED_NOW,
    facilitator,
    parchi_domain,
    supervisor,
    worker,
)
from tests.support.explanation_builders import faithful_response, resolved_result
from tests.support.stub_authz import StubAuthzProvider


def build(*, deny_actions=frozenset(), model=None):
    model = model or FakeExplanationModel(responder=faithful_response)
    service = ExplanationService(
        authorization=AuthorizationService(
            authz=StubAuthzProvider(deny_actions=frozenset(deny_actions))
        ),
        model=model,
    )
    return service, model


def test_an_authorized_supervisor_gets_an_explanation_and_the_model_is_called():
    service, model = build()
    outcome = service.explain_site(
        principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW
    )
    assert outcome.is_available
    assert len(model.calls) == 1


def test_a_denied_site_view_raises_and_never_calls_the_model():
    service, model = build(deny_actions={VIEW_SITE_EXECUTION})
    with pytest.raises(AuthorizationDenied):
        service.explain_site(principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW)
    assert model.calls == []


def test_a_worker_may_explain_their_own_parchi():
    service, model = build()
    outcome = service.explain_parchi(
        principal=worker("wrk-1"), parchi=parchi_domain(worker_id="wrk-1"), now=FIXED_NOW
    )
    assert outcome.is_available
    assert len(model.calls) == 1


def test_a_facilitator_denied_view_parchi_cannot_get_an_explanation():
    service, model = build(deny_actions={VIEW_PARCHI})
    with pytest.raises(AuthorizationDenied):
        service.explain_parchi(
            principal=facilitator("fac-1"), parchi=parchi_domain(worker_id="wrk-1"), now=FIXED_NOW
        )
    assert model.calls == []


def test_the_action_used_for_a_site_explanation_is_view_site_execution():
    provider = StubAuthzProvider()
    service = ExplanationService(
        authorization=AuthorizationService(authz=provider),
        model=FakeExplanationModel(responder=faithful_response),
    )
    service.explain_site(principal=supervisor(), result=resolved_result(stage=3), now=FIXED_NOW)
    assert provider.requests[-1][1] == VIEW_SITE_EXECUTION
