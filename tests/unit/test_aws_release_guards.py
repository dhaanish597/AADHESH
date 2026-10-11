"""Regression coverage for role fail-closed behavior and production write boundaries."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aadesh_aws import api_handler
from aadesh_aws.api_handler import PrincipalClaimError, _principal
from aadesh_core.domain import Principal, SourceState
from aadesh_core.errors import (
    AuthorizationDenied,
    CorpusIntegrityError,
    OperationalWriteDenied,
)
from aadesh_web.server import SITE_ID, SUPERVISOR_ID, Demo
from tests.support.builders import invoked_stage, snapshot


def _event(path: str, *, claims: dict, method: str = "GET", body: dict | None = None) -> dict:
    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body or {}),
        "requestContext": {"authorizer": {"claims": {"sub": "cognito-sub", **claims}}},
    }


def _supervisor_claims(**overrides) -> dict:
    return {
        "custom:role": "supervisor",
        "custom:assigned_site": SITE_ID,
        "custom:principal_id": SUPERVISOR_ID,
        **overrides,
    }


def _body(response: dict) -> dict:
    return json.loads(response["body"])


def test_missing_and_unknown_cognito_roles_fail_closed():
    for claims in ({}, {"custom:role": "root"}):
        with pytest.raises(PrincipalClaimError):
            _principal(_event("/api/roster/qr", claims=claims))


def test_supervisor_role_requires_assigned_site():
    with pytest.raises(PrincipalClaimError):
        _principal(
            _event(
                "/api/roster/qr",
                claims={"custom:role": "supervisor", "custom:principal_id": "sup-1"},
            )
        )


def test_authenticated_supervisor_cannot_select_another_roster_site(monkeypatch):
    app = Demo()
    app.create_standing_order(scenario="replay")
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)

    response = api_handler.handle(
        _event(
            "/api/roster/qr",
            claims=_supervisor_claims(),
            method="POST",
            body={"site_id": "another-site"},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "AUTHORIZATION_DENIED"


def test_api_rejects_missing_claim_role_even_if_body_claims_supervisor(monkeypatch):
    app = Demo()
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)

    response = api_handler.handle(
        _event(
            "/api/roster/qr",
            claims={},
            method="POST",
            body={"role": "supervisor", "principal_id": SUPERVISOR_ID, "site_id": SITE_ID},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response) == {
        "error": "INVALID_PRINCIPAL",
        "reason": "A provisioned role and identity are required.",
    }


def test_authenticated_worker_cannot_access_supervisor_roster_or_qrs(monkeypatch):
    app = Demo()
    app.create_standing_order(scenario="replay")
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)

    worker_claims = {"custom:role": "worker", "custom:principal_id": "worker-001"}
    token_count = len(app.tokens._tokens)
    for method, path in (("GET", "/api/roster"), ("POST", "/api/roster/qr")):
        response = api_handler.handle(
            _event(
                path,
                claims=worker_claims,
                method=method,
                body={"role": "supervisor", "principal_id": SUPERVISOR_ID, "site_id": SITE_ID},
            )
        )
        assert response["statusCode"] == 403
        assert _body(response)["error"] == "AUTHORIZATION_DENIED"
    assert len(app.tokens._tokens) == token_count


def test_wrong_site_supervisor_cannot_read_roster_or_mint_qrs(monkeypatch):
    app = Demo()
    app.create_standing_order(scenario="replay")
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    token_count = len(app.tokens._tokens)
    event = _event(
        "/api/roster/qr",
        claims=_supervisor_claims(**{"custom:assigned_site": "another-site"}),
        method="POST",
        body={"site_id": SITE_ID},
    )

    response = api_handler.handle(event)

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "AUTHORIZATION_DENIED"
    assert len(app.tokens._tokens) == token_count


def test_authorized_supervisor_can_retrieve_site_qrs(monkeypatch):
    app = Demo()
    app.create_standing_order(scenario="replay")
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)

    response = api_handler.handle(
        _event(
            "/api/roster/qr",
            claims=_supervisor_claims(),
            method="POST",
            body={"site_id": SITE_ID, "scenario": "replay"},
        )
    )

    assert response["statusCode"] == 200
    assert _body(response)["qr_minted"] > 0


def _production_demo() -> Demo:
    return Demo(allow_demo_replay_writes=False)


def test_production_application_refuses_replay_order_and_parchis_before_writes():
    app = _production_demo()
    supervisor = Principal(SUPERVISOR_ID, "supervisor", SITE_ID)

    with pytest.raises(OperationalWriteDenied):
        app.create_standing_order(scenario="replay", principal=supervisor)
    with pytest.raises(OperationalWriteDenied):
        app.open_parchis(scenario="replay")

    assert app.store.for_site(SITE_ID) == ()
    assert app._current_order() is None


def test_production_api_returns_stable_denial_for_historical_order_write(monkeypatch):
    app = _production_demo()
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)

    response = api_handler.handle(
        _event(
            "/api/standing-order",
            claims=_supervisor_claims(),
            method="POST",
            body={"scenario": "replay"},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "OPERATIONAL_WRITE_DENIED"
    assert app.store.for_site(SITE_ID) == ()
    assert app._current_order() is None


def test_worker_cannot_create_a_standing_order_even_with_current_scenario():
    app = _production_demo()
    worker = Principal("worker-001", "worker")

    with pytest.raises(AuthorizationDenied):
        app.create_standing_order(scenario="current", principal=worker)

    assert app.store.for_site(SITE_ID) == ()


class _VerifiedCurrentCorpus:
    def __init__(self) -> None:
        self._stage = invoked_stage(invoked_at=datetime.now(UTC) - timedelta(hours=1))
        self._snapshot = snapshot(stage=self._stage)

    def snapshot(self):
        return self._snapshot

    def invoked_stage(self):
        return self._stage

    def invocation_history(self):
        return (self._stage,)

    def obligations(self):
        return ()

    def entitlements(self):
        return ()

    def stage_bands(self):
        return ()

    def documents(self):
        return ()


def test_verified_current_official_stage_can_create_the_existing_stage_three_order():
    app = _production_demo()
    corpus = _VerifiedCurrentCorpus()
    app._corpus = lambda: corpus
    supervisor = Principal(SUPERVISOR_ID, "supervisor", SITE_ID)

    order = app.create_standing_order(scenario="current", principal=supervisor)

    assert order.trigger.stage == 3
    assert app.operational_invocation is corpus.invoked_stage()
    assert app.operational_invocation.source_state is SourceState.VERIFIED
    assert app.store.for_site(SITE_ID)


def test_revoked_current_invocation_is_a_stable_operational_denial():
    app = _production_demo()
    # The repository corpus is a proved historical/revoked invocation, not a current one.
    with pytest.raises(OperationalWriteDenied):
        app.create_standing_order(
            scenario="current",
            principal=Principal(SUPERVISOR_ID, "supervisor", SITE_ID),
        )
    assert app.store.for_site(SITE_ID) == ()
    assert app._current_order() is None


def test_missing_current_invocation_is_a_stable_operational_denial():
    app = _production_demo()

    class EmptyCorpus:
        def snapshot(self):
            return snapshot()

        def obligations(self):
            return ()

    app._corpus = lambda: EmptyCorpus()
    with pytest.raises(OperationalWriteDenied):
        app.create_standing_order(
            scenario="current",
            principal=Principal(SUPERVISOR_ID, "supervisor", SITE_ID),
        )
    assert app.store.for_site(SITE_ID) == ()


def test_unverifiable_current_invocation_is_a_stable_operational_denial():
    app = _production_demo()

    class BrokenCorpus:
        def snapshot(self):
            raise CorpusIntegrityError("private verification detail")

        def obligations(self):
            return ()

    app._corpus = lambda: BrokenCorpus()
    with pytest.raises(OperationalWriteDenied) as denied:
        app.create_standing_order(
            scenario="current",
            principal=Principal(SUPERVISOR_ID, "supervisor", SITE_ID),
        )

    assert str(denied.value) == (
        "No verified current Stage III invocation is available; no operational records were created."
    )
    assert app.store.for_site(SITE_ID) == ()


def test_production_build_scripts_force_demo_mode_off(repo_root: Path):
    for path in (repo_root / "amplify.yml", repo_root / "infra/aws/deploy-web.sh"):
        source = path.read_text(encoding="utf-8")
        assert "NEXT_PUBLIC_AADESH_DEMO=0" in source
        assert "NEXT_PUBLIC_AADESH_DEMO=1" not in source


def test_cognito_uses_admin_only_signup_and_client_cannot_write_role_attributes(repo_root: Path):
    template = (repo_root / "infra/aws/template.yaml").read_text(encoding="utf-8")
    assert "AdminCreateUserConfig:\n        AllowAdminCreateUserOnly: true" in template
    client_config = template.split("  UserPoolClient:\n", 1)[1].split("  # ===", 1)[0]
    write_attributes = client_config.split("      WriteAttributes:\n", 1)[1].split(
        "      CallbackURLs:", 1
    )[0]
    assert write_attributes.strip() == "- email"
    for attribute in ("custom:role", "custom:assigned_site", "custom:principal_id"):
        assert attribute not in write_attributes


def test_local_demo_still_allows_read_only_replay_and_explicit_demo_workflow(repo_root):
    app = Demo(corpus_root=repo_root / "corpus")
    view = app.supervisor(scenario="replay")
    assert view["stage_detail"]["is_replay"] is True
    order = app.create_standing_order(scenario="replay")
    assert order.signed_at is not None
    assert app.store.for_site(SITE_ID)
