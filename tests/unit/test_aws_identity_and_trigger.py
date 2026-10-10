"""INVARIANT: on AWS the principal comes from verified claims, and a run starts from an event.

Two defects are pinned here, and both only become visible once a REAL principal exists -- which
is why the local demonstration path never caught them:

  * `create_standing_order` signs as the principal it is given. With the Cognito `sub` as the
    principal id, a signed-in supervisor's own pre-commitment was refused with
    "only supervisor '<the demo id>' may sign it" -- the supervisor could not sign the halt the
    entire product exists to issue.
  * what starts the workflow is a published `StageInvocation` event: the API holds no
    `states:StartExecution` and calls it nowhere. A publish that fails must be REPORTED, because
    the signed order and its opened Parchis are already facts -- telling the supervisor they do
    not exist would be false.

The publish test injects a fake client, so `make test` still touches no AWS API.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aadesh_aws.api_handler import _principal
from aadesh_aws.events import publish_stage_invocation
from aadesh_core.domain import Principal
from aadesh_core.errors import AuthorizationDenied
from aadesh_web.server import SITE_ID, SUPERVISOR_ID, Demo

SITE = "example-piling-site"


# --------------------------------------------------------------------------- identity


def _claims_event(**claims: Any) -> dict[str, Any]:
    """An API Gateway event whose authorizer has already verified these claims."""
    return {
        "httpMethod": "POST",
        "path": "/api/standing-order",
        # A caller naming themselves in the body must change nothing.
        "body": json.dumps({"worker_id": "worker-009", "principal_id": "worker-009"}),
        "requestContext": {"authorizer": {"claims": {"sub": "cognito-sub-uuid", **claims}}},
    }


def test_principal_id_comes_from_the_claim_not_the_cognito_sub():
    """`resource.worker == principal` is ENTITY equality, so the id must be the pool's."""
    principal = _principal(
        _claims_event(**{"custom:role": "worker", "custom:principal_id": "worker-001"}),
        default_role="worker",
    )

    assert principal is not None
    assert principal.principal_id == "worker-001"
    assert principal.principal_id != "cognito-sub-uuid"


def test_principal_id_falls_back_to_sub_when_the_pool_has_no_such_attribute():
    """A pool without the attribute still yields a usable principal, never None."""
    principal = _principal(
        _claims_event(**{"custom:role": "facilitator"}), default_role="facilitator"
    )

    assert principal is not None
    assert principal.principal_id == "cognito-sub-uuid"
    assert principal.role == "facilitator"


def test_a_body_supplied_identity_is_ignored():
    """The request body cannot name a principal; only the verified claims can."""
    principal = _principal(
        _claims_event(**{"custom:role": "worker", "custom:principal_id": "worker-001"}),
        default_role="worker",
    )

    assert principal is not None
    assert principal.principal_id != "worker-009"


def test_no_authorizer_claim_means_no_principal():
    """The two routes that are not behind the authorizer get None, and the app falls back."""
    assert _principal({"httpMethod": "GET", "path": "/api/health"}, default_role="worker") is None


def test_role_and_site_come_from_the_verified_claims():
    principal = _principal(
        _claims_event(
            **{
                "custom:role": "supervisor",
                "custom:assigned_site": SITE,
                "custom:principal_id": SUPERVISOR_ID,
            }
        ),
        default_role="supervisor",
    )

    assert principal is not None
    assert (principal.role, principal.assigned_site) == ("supervisor", SITE)


# --------------------------------------------------------------------------- signing


def test_a_signed_in_supervisor_signs_their_own_order(repo_root):
    """The bug this pins: signing used the configured demo id, not the principal's."""
    app = Demo(corpus_root=repo_root / "corpus")
    who = Principal(principal_id="supervisor-aadesh", role="supervisor", assigned_site=SITE_ID)

    order = app.create_standing_order(scenario="replay", principal=who)

    assert order.supervisor_id == "supervisor-aadesh"
    assert order.signed_at is not None
    assert order.commitment_hash


def test_the_demonstration_principal_still_signs_the_same_order(repo_root):
    """The local skin passes no principal; the order must be signed by the configured one."""
    app = Demo(corpus_root=repo_root / "corpus")

    order = app.create_standing_order(scenario="replay")

    assert order.supervisor_id == SUPERVISOR_ID


def test_a_supervisor_of_another_site_cannot_sign_here(repo_root):
    """Cedar still decides: identity became real without widening who may issue a halt."""
    app = Demo(corpus_root=repo_root / "corpus")
    who = Principal(
        principal_id="supervisor-elsewhere", role="supervisor", assigned_site="other-site"
    )

    with pytest.raises(AuthorizationDenied):
        app.create_standing_order(scenario="replay", principal=who)


# --------------------------------------------------------------------------- the trigger


class _FakeEvents:
    def __init__(self, *, failed: bool = False, raises: bool = False) -> None:
        self.entries: list[dict[str, Any]] = []
        self._failed = failed
        self._raises = raises

    def put_events(self, *, Entries: list[dict[str, Any]]) -> dict[str, Any]:
        if self._raises:
            raise RuntimeError("event bus unavailable")
        self.entries.extend(Entries)
        if self._failed:
            return {
                "FailedEntryCount": 1,
                "Entries": [{"ErrorCode": "ThrottlingException", "ErrorMessage": "slow down"}],
            }
        return {"FailedEntryCount": 0, "Entries": [{"EventId": "evt-1"}]}


def test_the_published_event_carries_the_key_the_api_opened_parchis_under():
    """The machine's CreateParchis step must find the API's Parchis, not mint a second set."""
    client = _FakeEvents()

    result = publish_stage_invocation(
        order_id="so-1",
        site_id=SITE,
        scenario="replay",
        execution_id="exec-so-1",
        stage=3,
        order_doc_id="caqm-grap-stage3-order-2026-01-16",
        order_sha256="a" * 64,
        client=client,
    )

    assert result["published"] is True
    entry = client.entries[0]
    assert entry["Source"] == "aadesh.events"
    assert entry["DetailType"] == "StageInvocation"
    detail = json.loads(entry["Detail"])
    assert detail["execution_id"] == "exec-so-1"
    assert detail["order_id"] == "so-1"
    assert detail["scenario"] == "replay"


def test_a_rejected_event_is_reported_and_never_raised():
    """A failed publish is a fact about the run; the Parchis still exist."""
    result = publish_stage_invocation(
        order_id="so-1",
        site_id=SITE,
        scenario="replay",
        execution_id="exec-so-1",
        client=_FakeEvents(failed=True),
    )

    assert result["published"] is False
    assert "ThrottlingException" in result["reason"]


def test_an_unreachable_event_bus_is_reported_and_never_raised():
    result = publish_stage_invocation(
        order_id="so-1",
        site_id=SITE,
        scenario="replay",
        execution_id="exec-so-1",
        client=_FakeEvents(raises=True),
    )

    assert result["published"] is False
    assert "RuntimeError" in result["reason"]
