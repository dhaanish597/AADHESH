"""INVARIANT: AllowAllTestOnly cannot load outside the test environment.

An authorization provider that permits everything is a useful test fixture and a catastrophic
production component. The gap between those two is one environment variable and one hurried
deployment, so the component refuses to construct unless AADESH_ENV is exactly "test".

It is named to be embarrassing on purpose.
"""

from __future__ import annotations

import pytest

from aadesh_adapters.authz.test_only import AllowAllTestOnly
from aadesh_core.domain import Principal
from aadesh_core.errors import TestOnlyComponentInProduction
from aadesh_core.ports.authz import AuthzResource

ANY_PRINCIPAL = Principal(principal_id="anyone", role="worker")
ANY_RESOURCE = AuthzResource(entity_type="Parchi", entity_id="p-1", attributes={})


def test_constructs_when_env_is_test(monkeypatch):
    monkeypatch.setenv("AADESH_ENV", "test")
    assert AllowAllTestOnly() is not None


@pytest.mark.parametrize("env", ["local", "aws", "production", "prod", "Test", "TEST", ""])
def test_refuses_to_construct_outside_test(monkeypatch, env):
    monkeypatch.setenv("AADESH_ENV", env)
    with pytest.raises(TestOnlyComponentInProduction, match="AADESH_ENV"):
        AllowAllTestOnly()


def test_refuses_to_construct_when_env_is_unset(monkeypatch):
    """An unset variable must not be read as permission."""
    monkeypatch.delenv("AADESH_ENV", raising=False)
    with pytest.raises(TestOnlyComponentInProduction):
        AllowAllTestOnly()


def test_it_really_does_allow_everything(monkeypatch):
    """Proves the guard is protecting against a real hazard, not a hypothetical one."""
    monkeypatch.setenv("AADESH_ENV", "test")
    provider = AllowAllTestOnly()
    for action in ["AcknowledgeOwnParchi", "ViewParchi", "IssueHalt", "AssistClaim"]:
        decision = provider.authorize(principal=ANY_PRINCIPAL, action=action, resource=ANY_RESOURCE)
        assert decision.allowed is True


def test_its_decisions_are_labelled_as_unsafe(monkeypatch):
    monkeypatch.setenv("AADESH_ENV", "test")
    decision = AllowAllTestOnly().authorize(
        principal=ANY_PRINCIPAL, action="AcknowledgeOwnParchi", resource=ANY_RESOURCE
    )
    assert "test" in decision.reason.lower()
