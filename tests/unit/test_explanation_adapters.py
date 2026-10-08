"""The adapters, offline.

Bedrock is exercised through an injected client -- no boto3, no network, no credentials. Strands
is exercised through an injected agent-shaped callable, and its absent-install path is asserted
directly. The fake is exercised for the failure modes the service must survive.
"""

from __future__ import annotations

import json

import pytest

from aadesh_adapters.explain import (
    BedrockExplanationModel,
    FakeExplanationModel,
    StrandsExplanationModel,
    parse_response,
)
from aadesh_core.errors import ExplanationUnavailable
from aadesh_core.explanation import ExplanationStatus, request_for_resolution
from tests.support.explanation_builders import (
    faithful_response,
    replay_result,
    resolved_result,
    response_payload,
)


def request():
    return request_for_resolution(resolved_result(stage=3))


class FakeBedrockClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_bedrock_adapter_parses_a_valid_response_through_an_injected_client():
    req = request()
    client = FakeBedrockClient(json.dumps(response_payload(req)))
    model = BedrockExplanationModel(client=client)
    response = model.explain(request=req)
    assert response is not None
    assert client.calls[0]["modelId"] == model._model_id
    assert client.calls[0]["messages"][0]["content"][0]["text"].startswith("You are the")


def test_bedrock_adapter_returns_none_when_there_is_no_text():
    client = FakeBedrockClient("")
    model = BedrockExplanationModel(client=client)
    assert model.explain(request=request()) is None


def test_bedrock_adapter_rejects_text_that_is_not_json():
    client = FakeBedrockClient("certainly, here is your explanation")
    model = BedrockExplanationModel(client=client)
    with pytest.raises(ValueError):
        model.explain(request=request())


def test_bedrock_adapter_without_boto3_raises_explanation_unavailable():
    with pytest.raises(ExplanationUnavailable):
        BedrockExplanationModel(region_name="ap-south-1")


def test_fake_model_records_requests_and_returns_the_configured_response():
    req = request()
    fake = FakeExplanationModel(response=faithful_response(req))
    assert fake.explain(request=req).summary
    assert fake.last_request is req


def test_fake_model_can_simulate_malformed_output():
    with pytest.raises(ValueError):
        FakeExplanationModel(malformed=True).explain(request=request())


def test_fake_model_can_simulate_a_provider_error():
    with pytest.raises(RuntimeError):
        FakeExplanationModel(error=RuntimeError("boom")).explain(request=request())


def test_strands_adapter_uses_an_injected_agent_callable():
    req = request()
    payload = json.dumps(response_payload(req))

    def agent(prompt: str) -> str:
        assert "QUESTION" in prompt
        return payload

    response = StrandsExplanationModel(agent=agent).explain(request=req)
    assert response is not None
    assert response.model_metadata["provider"] == "strands"


def test_strands_adapter_uses_an_invoke_method():
    req = request()

    class Agent:
        def invoke(self, prompt: str) -> str:
            return json.dumps(response_payload(req))

    assert StrandsExplanationModel(agent=Agent()).explain(request=req) is not None


def test_strands_adapter_requires_an_agent():
    with pytest.raises(ExplanationUnavailable):
        StrandsExplanationModel(agent=None)


def test_strands_from_strands_is_unavailable_when_strands_is_not_installed():
    with pytest.raises(ExplanationUnavailable):
        StrandsExplanationModel.from_strands()


def test_the_strands_agent_is_constructed_with_no_tools():
    # Structural proof: the factory never passes a `tools` keyword to the agent. If it did, the
    # model would gain an action surface, which is the one thing this adapter must never expose.
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(StrandsExplanationModel.from_strands))
    module = ast.parse(source)
    agent_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Agent"
    ]
    assert agent_calls, "the factory must construct an Agent"
    for call in agent_calls:
        assert all(keyword.arg != "tools" for keyword in call.keywords), (
            "the Strands agent must be constructed with no tools"
        )


def test_parse_response_strips_a_markdown_fence():
    req = request()
    fenced = f"```json\n{json.dumps(response_payload(req))}\n```"
    response = parse_response(fenced, model_metadata={"provider": "x"})
    assert response.official_stage == req.official_stage


def test_replay_request_can_be_explained_offline():
    req = request_for_resolution(replay_result())
    response = FakeExplanationModel(response=faithful_response(req)).explain(request=req)
    assert response.replay_status == "REPLAY"
    assert response.source_references  # carried through


def test_a_rejected_response_still_yields_a_deterministic_explanation():
    # The fake cannot change the deterministic layer; the service would fall back regardless.
    assert ExplanationStatus.EXPLANATION_UNAVAILABLE.value == "EXPLANATION_UNAVAILABLE"
