"""INVARIANT: the two Cedar forbid rules are actually enforced.

These run against the REAL Cedar 4.x engine via cedarpy, not a stub. That matters: a policy
file nobody evaluates is documentation, and the whole argument for putting authorization in
Cedar rather than in `if` statements is that the policy is the thing that runs.

The two forbid rules are product behaviour:

  * `no-proxy-acknowledgement` -- a supervisor cannot complete a worker's acknowledgement.
    Without it the parchi proves nothing, because the person with the phone could click
    through 34 confirmations alone.
  * `assist-is-not-disclosure` -- a facilitator who is explicitly asked for help still
    cannot read the worker's record. Opting in to help is not opting in to disclosure.
"""

from __future__ import annotations

import json

import pytest

from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_core.domain import Principal
from aadesh_core.ports.authz import AuthzResource, EntityRef

SUPERVISOR = Principal(principal_id="sup-1", role="supervisor", assigned_site="site-001")
WORKER = Principal(principal_id="wrk-1", role="worker")
OTHER_WORKER = Principal(principal_id="wrk-2", role="worker")
FACILITATOR = Principal(principal_id="fac-1", role="facilitator")


def parchi_resource(*, worker_id="wrk-1", site_id="site-001", shared=False) -> AuthzResource:
    return AuthzResource(
        entity_type="Parchi",
        entity_id="parchi-001",
        attributes={
            "worker": EntityRef("Principal", worker_id),
            "siteId": site_id,
            "sharedForAssistance": shared,
        },
    )


def site_resource(site_id="site-001") -> AuthzResource:
    return AuthzResource(entity_type="Site", entity_id=site_id, attributes={"siteId": site_id})


@pytest.fixture(scope="module")
def authz(repo_root):
    return CedarAuthorizationProvider(
        policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
        denials_path=repo_root / "infra" / "cedar" / "denials.json",
        schema_path=repo_root / "infra" / "cedar" / "schema.cedarschema.json",
    )


# --- the two forbid rules --------------------------------------------------


def test_supervisor_cannot_acknowledge_on_a_workers_behalf(authz):
    decision = authz.authorize(principal=SUPERVISOR, action="AckParchi", resource=parchi_resource())
    assert decision.allowed is False
    assert decision.policy_id == "no-proxy-acknowledgement"
    assert "on a worker's behalf" in decision.reason


def test_another_worker_cannot_acknowledge_it_either(authz):
    decision = authz.authorize(
        principal=OTHER_WORKER, action="AckParchi", resource=parchi_resource()
    )
    assert decision.allowed is False
    assert decision.policy_id == "no-proxy-acknowledgement"


def test_facilitator_cannot_read_a_parchi_even_when_it_is_shared(authz):
    """The interesting case. Sharing grants assistance, not disclosure."""
    decision = authz.authorize(
        principal=FACILITATOR, action="ViewParchi", resource=parchi_resource(shared=True)
    )
    assert decision.allowed is False
    assert decision.policy_id == "assist-is-not-disclosure"
    assert "not opting in to disclosure" in decision.reason


def test_forbid_beats_permit(authz):
    """A facilitator permitted to AssistClaim is still forbidden to ViewParchi."""
    shared = parchi_resource(shared=True)
    assert (
        authz.authorize(principal=FACILITATOR, action="AssistClaim", resource=shared).allowed
        is True
    )
    assert (
        authz.authorize(principal=FACILITATOR, action="ViewParchi", resource=shared).allowed
        is False
    )


# --- the permits -----------------------------------------------------------


def test_worker_may_acknowledge_their_own_parchi(authz):
    decision = authz.authorize(
        principal=WORKER, action="AckParchi", resource=parchi_resource(worker_id="wrk-1")
    )
    assert decision.allowed is True


def test_worker_may_view_their_own_parchi(authz):
    assert (
        authz.authorize(principal=WORKER, action="ViewParchi", resource=parchi_resource()).allowed
        is True
    )


def test_supervisor_may_issue_a_halt_for_their_own_site(authz):
    assert (
        authz.authorize(
            principal=SUPERVISOR, action="IssueHalt", resource=site_resource("site-001")
        ).allowed
        is True
    )


def test_supervisor_may_not_issue_a_halt_for_another_site(authz):
    decision = authz.authorize(
        principal=SUPERVISOR, action="IssueHalt", resource=site_resource("site-999")
    )
    assert decision.allowed is False


def test_facilitator_may_not_assist_an_unshared_claim(authz):
    decision = authz.authorize(
        principal=FACILITATOR, action="AssistClaim", resource=parchi_resource(shared=False)
    )
    assert decision.allowed is False


def test_supervisor_without_an_assigned_site_is_denied(authz):
    """`assignedSite` is optional on Principal; a role claim alone must grant nothing."""
    rogue = Principal(principal_id="sup-9", role="supervisor", assigned_site=None)
    assert (
        authz.authorize(
            principal=rogue, action="IssueHalt", resource=site_resource("site-001")
        ).allowed
        is False
    )


# --- denials are sentences, not codes --------------------------------------


def test_an_implicit_denial_still_produces_a_human_sentence(authz):
    decision = authz.authorize(
        principal=WORKER, action="IssueHalt", resource=site_resource("site-001")
    )
    assert decision.allowed is False
    assert decision.policy_id is None
    assert decision.reason.endswith(".")
    assert "Cedar denied this" in decision.reason


def test_every_forbid_policy_has_denial_copy(repo_root, authz):
    denials = json.loads(
        (repo_root / "infra" / "cedar" / "denials.json").read_text(encoding="utf-8")
    )
    missing = [a for a in authz.forbid_annotations if a not in denials]
    assert missing == [], f"forbid policies with no human sentence: {missing}"


def test_policies_validate_against_the_schema(authz):
    """A policy that does not typecheck against the schema is a latent authorization bug."""
    assert authz.validate() == []
