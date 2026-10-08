"""The Prompt 6 authorization model, exercised against the real Cedar engine.

These are the rules the brief calls out by name, written as authorization questions rather
than as UI behaviour: every assertion below is about a DECISION, so none of them can be
satisfied by hiding a button.

The consent cases are the ones worth reading closely. A worker granting assistance has to
expire and be revocable, and both facts have to be decided by the POLICY. That is why the
request carries `context={"now": ...}`: Cedar has no clock, so the caller supplies the
instant and the policy compares it. If expiry were computed in Python and handed to Cedar
as a boolean, the rule would live outside the thing being audited.
"""

from __future__ import annotations

import pytest

from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from tests.support.authz_builders import (
    claim_context_resource,
    facilitator,
    parchi_resource,
    site_resource,
    supervisor,
    worker,
)

PRINCIPAL = "Principal"


@pytest.fixture(scope="module")
def authz(repo_root) -> CedarAuthorizationProvider:
    return CedarAuthorizationProvider(
        policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
        denials_path=repo_root / "infra" / "cedar" / "denials.json",
        schema_path=repo_root / "infra" / "cedar" / "schema.cedarschema.json",
    )


def decide(authz: CedarAuthorizationProvider, principal, action, resource, *, now: int = 1_500):
    return authz.authorize(
        principal=principal, action=action, resource=resource, context={"now": now}
    )


# ---------------------------------------------------------------------------
# Rule 1 -- a supervisor halts their own site, and only their own site
# ---------------------------------------------------------------------------


def test_supervisor_issues_halt_for_a_site_they_supervise(authz):
    decision = decide(authz, supervisor(site="site-001"), "IssueHalt", site_resource("site-001"))
    assert decision.allowed is True


def test_supervisor_issues_halt_for_an_unrelated_site(authz):
    decision = decide(authz, supervisor(site="site-001"), "IssueHalt", site_resource("site-999"))
    assert decision.allowed is False


def test_supervisor_views_execution_for_their_own_site(authz):
    decision = decide(
        authz, supervisor(site="site-001"), "ViewSiteExecution", site_resource("site-001")
    )
    assert decision.allowed is True


def test_supervisor_views_execution_for_an_unrelated_site(authz):
    decision = decide(
        authz, supervisor(site="site-001"), "ViewSiteExecution", site_resource("site-999")
    )
    assert decision.allowed is False


def test_a_worker_cannot_view_a_site_execution(authz):
    """Not every role reaches every action: the supervisor-only actions are supervisor-only."""
    decision = decide(authz, worker(), "ViewSiteExecution", site_resource("site-001"))
    assert decision.allowed is False


# ---------------------------------------------------------------------------
# Rules 2 and 3 -- the worker acknowledges their own parchi; nobody else can
# ---------------------------------------------------------------------------


def test_worker_acknowledges_their_own_parchi(authz):
    decision = decide(
        authz, worker("wrk-1"), "AcknowledgeOwnParchi", parchi_resource(worker_id="wrk-1")
    )
    assert decision.allowed is True


def test_a_different_worker_cannot_acknowledge_it(authz):
    """Same site, same contractor, valid token -- and still refused, on identity alone."""
    decision = decide(
        authz,
        worker("wrk-2"),
        "AcknowledgeOwnParchi",
        parchi_resource(worker_id="wrk-1", site_id="site-001"),
    )
    assert decision.allowed is False


def test_a_supervisor_cannot_acknowledge_for_a_worker(authz):
    """The deliberate asymmetric-power boundary. The supervisor may issue the halt that
    produced this parchi and still may not complete it."""
    decision = decide(
        authz,
        supervisor("sup-1", site="site-001"),
        "AcknowledgeOwnParchi",
        parchi_resource(worker_id="wrk-1", site_id="site-001"),
    )
    assert decision.allowed is False
    assert decision.policy_id == "no-proxy-acknowledgement"


def test_a_facilitator_cannot_acknowledge_a_parchi(authz):
    decision = decide(
        authz, facilitator(), "AcknowledgeOwnParchi", parchi_resource(worker_id="wrk-1")
    )
    assert decision.allowed is False


# ---------------------------------------------------------------------------
# Rules 4 and 5 -- consent gates assistance, and assistance is not disclosure
# ---------------------------------------------------------------------------


def test_facilitator_assists_with_a_live_consent(authz):
    decision = decide(
        authz,
        facilitator("fac-1"),
        "AssistClaim",
        claim_context_resource(facilitator_id="fac-1", granted_at=1_000, expires_at=2_000),
        now=1_500,
    )
    assert decision.allowed is True


def test_facilitator_without_consent_is_denied(authz):
    decision = decide(
        authz,
        facilitator("fac-1"),
        "AssistClaim",
        claim_context_resource(facilitator_id="fac-1", consent_granted=False),
        now=1_500,
    )
    assert decision.allowed is False


def test_expired_consent_is_denied(authz):
    """Granted, never revoked, and still refused -- because the instant is past expiry.
    This is the case a boolean `sharedForAssistance` flag cannot express."""
    decision = decide(
        authz,
        facilitator("fac-1"),
        "AssistClaim",
        claim_context_resource(facilitator_id="fac-1", granted_at=1_000, expires_at=2_000),
        now=2_001,
    )
    assert decision.allowed is False


def test_revoked_consent_is_denied(authz):
    """Revoked before it expired: the worker withdrew it while it was still live."""
    decision = decide(
        authz,
        facilitator("fac-1"),
        "AssistClaim",
        claim_context_resource(
            facilitator_id="fac-1", granted_at=1_000, expires_at=2_000, revoked_at=1_200
        ),
        now=1_500,
    )
    assert decision.allowed is False


def test_consent_granted_in_the_future_is_denied(authz):
    """A context that has not started yet authorizes nothing. Without the `grantedAt`
    bound, a mis-dated context would grant access early and silently."""
    decision = decide(
        authz,
        facilitator("fac-1"),
        "AssistClaim",
        claim_context_resource(facilitator_id="fac-1", granted_at=1_900, expires_at=2_000),
        now=1_500,
    )
    assert decision.allowed is False


def test_a_different_facilitator_cannot_use_someone_elses_consent(authz):
    """Consent is granted to a person, not broadcast to a role."""
    decision = decide(
        authz,
        facilitator("fac-2"),
        "AssistClaim",
        claim_context_resource(facilitator_id="fac-1"),
        now=1_500,
    )
    assert decision.allowed is False


def test_a_facilitator_cannot_view_the_parchi_even_with_live_consent(authz):
    """The demo line: facilitator can assist, cannot see the worker's complete parchi.
    `forbid` beats `permit`, so holding a live consent does not open the record."""
    assert (
        decide(
            authz,
            facilitator("fac-1"),
            "AssistClaim",
            claim_context_resource(facilitator_id="fac-1"),
            now=1_500,
        ).allowed
        is True
    )
    decision = decide(authz, facilitator("fac-1"), "ViewParchi", parchi_resource(worker_id="wrk-1"))
    assert decision.allowed is False
    assert decision.policy_id == "assist-is-not-disclosure"


def test_a_worker_cannot_assist_a_claim(authz):
    """AssistClaim is the facilitator's action. A worker holding their own parchi does not
    thereby acquire it."""
    decision = decide(
        authz,
        worker("wrk-1"),
        "AssistClaim",
        claim_context_resource(worker_id="wrk-1", facilitator_id="fac-1"),
        now=1_500,
    )
    assert decision.allowed is False


def test_a_bare_parchi_confers_no_assistance(authz):
    """Assistance is requested against a ClaimAssistanceContext, never against a Parchi.

    This is the structural half of Rule 5: a facilitator who only ever holds a parchi
    reference has no way to name the AssistClaim at all, so there is no resource on which a
    permissive policy could accidentally match.
    """
    decision = decide(authz, facilitator("fac-1"), "AssistClaim", parchi_resource(), now=1_500)
    assert decision.allowed is False
