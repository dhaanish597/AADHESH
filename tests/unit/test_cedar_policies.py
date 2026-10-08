"""INVARIANT: the Cedar forbid rules are actually enforced.

These run against the REAL Cedar 4.x engine via cedarpy, not a stub. That matters: a policy
file nobody evaluates is documentation, and the whole argument for putting authorization in
Cedar rather than in `if` statements is that the policy is the thing that runs.

The forbid rules are product behaviour:

  * `no-proxy-acknowledgement` -- a supervisor cannot complete a worker's acknowledgement.
    Without it the parchi proves nothing, because the person with the phone could click
    through 34 confirmations alone.
  * `assist-is-not-disclosure` -- a facilitator who is explicitly asked for help still
    cannot read the worker's record. Opting in to help is not opting in to disclosure.
  * `assist-requires-live-consent` -- assistance is granted by a current consent and by
    nothing else.

Resource shapes are built by `tests.support.authz_builders`, so these tests and the Prompt 6
boundary tests cannot drift apart about what a "normal" parchi is.
"""

from __future__ import annotations

import json

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

SUPERVISOR = supervisor("sup-1", site="site-001")
WORKER = worker("wrk-1")
OTHER_WORKER = worker("wrk-2")
FACILITATOR = facilitator("fac-1")

#: Epoch seconds. Cedar core has no clock, so every request states its instant; consent
#: expiry is then decided by the policy comparing against it.
NOW = 1_700_000_000


@pytest.fixture(scope="module")
def authz(repo_root) -> CedarAuthorizationProvider:
    return CedarAuthorizationProvider(
        policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
        denials_path=repo_root / "infra" / "cedar" / "denials.json",
        schema_path=repo_root / "infra" / "cedar" / "schema.cedarschema.json",
    )


def ask(authz, principal, action, resource, *, now: int = NOW):
    return authz.authorize(
        principal=principal, action=action, resource=resource, context={"now": now}
    )


def live_consent(**overrides):
    """A consent that is granted, started and unexpired at `NOW`."""
    defaults = dict(granted_at=NOW - 60, expires_at=NOW + 86_400)
    defaults.update(overrides)
    return claim_context_resource(**defaults)


# --- the forbid rules ------------------------------------------------------


def test_supervisor_cannot_acknowledge_on_a_workers_behalf(authz):
    decision = ask(authz, SUPERVISOR, "AcknowledgeOwnParchi", parchi_resource())
    assert decision.allowed is False
    assert decision.policy_id == "no-proxy-acknowledgement"
    assert "on a worker's behalf" in decision.reason


def test_another_worker_cannot_acknowledge_it_either(authz):
    decision = ask(authz, OTHER_WORKER, "AcknowledgeOwnParchi", parchi_resource())
    assert decision.allowed is False
    assert decision.policy_id == "no-proxy-acknowledgement"


def test_facilitator_cannot_read_a_parchi_even_when_it_has_been_shared(authz):
    """The interesting case. Sharing grants assistance, not disclosure.

    The facilitator here holds a consent that is live at `NOW` -- the strongest position
    they can be in -- and the parchi is still closed to them.
    """
    assert ask(authz, FACILITATOR, "AssistClaim", live_consent()).allowed is True
    decision = ask(authz, FACILITATOR, "ViewParchi", parchi_resource())
    assert decision.allowed is False
    assert decision.policy_id == "assist-is-not-disclosure"
    assert "not opting in to disclosure" in decision.reason


def test_forbid_beats_permit(authz):
    """A facilitator permitted to AssistClaim is still forbidden to ViewParchi."""
    consent = live_consent()
    assert ask(authz, FACILITATOR, "AssistClaim", consent).allowed is True
    assert ask(authz, FACILITATOR, "ViewParchi", parchi_resource()).allowed is False


def test_a_consent_that_was_never_granted_confers_no_assistance(authz):
    decision = ask(authz, FACILITATOR, "AssistClaim", live_consent(consent_granted=False))
    assert decision.allowed is False
    assert decision.policy_id == "assist-requires-live-consent"


# --- the permits -----------------------------------------------------------


def test_worker_may_acknowledge_their_own_parchi(authz):
    decision = ask(authz, WORKER, "AcknowledgeOwnParchi", parchi_resource(worker_id="wrk-1"))
    assert decision.allowed is True


def test_worker_may_view_their_own_parchi(authz):
    assert ask(authz, WORKER, "ViewParchi", parchi_resource()).allowed is True


def test_supervisor_may_issue_a_halt_for_their_own_site(authz):
    assert ask(authz, SUPERVISOR, "IssueHalt", site_resource("site-001")).allowed is True


def test_supervisor_may_not_issue_a_halt_for_another_site(authz):
    decision = ask(authz, SUPERVISOR, "IssueHalt", site_resource("site-999"))
    assert decision.allowed is False


def test_facilitator_may_not_assist_without_consent(authz):
    decision = ask(authz, FACILITATOR, "AssistClaim", claim_context_resource(consent_granted=False))
    assert decision.allowed is False


def test_supervisor_without_an_assigned_site_is_denied(authz):
    """`assignedSite` is optional on Principal; a role claim alone must grant nothing."""
    rogue = supervisor("sup-9", site=None)
    assert ask(authz, rogue, "IssueHalt", site_resource("site-001")).allowed is False


# --- denials are sentences, not codes --------------------------------------


def test_an_implicit_denial_still_produces_a_human_sentence(authz):
    decision = ask(authz, WORKER, "IssueHalt", site_resource("site-001"))
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
