"""The Prompt 6 demo, as a deterministic test rather than a script.

Every scenario the brief names is here, and each one asserts a DECISION. That is deliberate:
a demo that proved "the button is gone" would pass just as happily against a system with no
authorization layer at all. These assert that the boundary refuses, and -- in the last case --
that it is not the only thing refusing.

The scenarios that matter most:

  * **5 vs 13.** A supervisor who issued the halt still cannot complete it, and a worker
    holding somebody else's valid link still cannot use it. Two independent mechanisms
    refusing the same act, which is the whole argument for not making Cedar the only lock.
  * **13, specifically.** The authorizer is replaced with one that permits EVERYTHING, and
    the domain still refuses a different worker. If Prompt 6 had moved the identity rule out
    of the domain and into policy, this test would fail -- and that is exactly the regression
    it is here to catch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.authz.test_only import AllowAllTestOnly
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.authorization.service import AuthorizationService
from aadesh_core.consent import grant_consent, request_assistance, revoke_consent
from aadesh_core.errors import (
    AuthorizationDenied,
    AuthorizationUnavailable,
    IllegalParchiTransition,
    WrongWorker,
)
from aadesh_core.parchi_ack import ParchiProvenance, RosterEntry, WorkflowExecution
from aadesh_core.parchi_ack.service import acknowledge_parchi
from aadesh_core.parchi_ack.workflow import create_parchi_for_worker
from tests.support.authz_builders import facilitator, supervisor, worker

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
SITE = "site-001"
OTHER_SITE = "site-999"

SUPERVISOR = supervisor("sup-1", site=SITE)
OTHER_SUPERVISOR = supervisor("sup-2", site=OTHER_SITE)
WORKER_A = worker("wrk-1")
WORKER_B = worker("wrk-2")
FACILITATOR = facilitator("fac-1")


@pytest.fixture(scope="module")
def cedar(repo_root) -> CedarAuthorizationProvider:
    return CedarAuthorizationProvider(
        policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
        denials_path=repo_root / "infra" / "cedar" / "denials.json",
        schema_path=repo_root / "infra" / "cedar" / "schema.cedarschema.json",
    )


@pytest.fixture
def service(cedar) -> AuthorizationService:
    return AuthorizationService(authz=cedar)


class _Unavailable:
    """A provider that cannot reach a decision. Stands in for a failed policy load, a
    corrupted policy set, or an engine that raised. It is defined here rather than shipped
    because nothing in production should ever need a way to be broken."""

    def authorize(self, *, principal, action, resource, context=None):
        raise AuthorizationUnavailable("the policy engine is not answering")


@pytest.fixture
def stores():
    return {
        "store": InMemoryParchiStore(),
        "tokens": InMemoryAcknowledgementTokenStore(),
        "ledger": InMemoryIdempotencyLedger(),
        "audit": RecordingAuditLog(),
    }


def _open_parchi(stores, *, worker_id="wrk-1", site_id=SITE, execution_id="exec-1"):
    """Open a real PENDING_ACK parchi and return (parchi, qr payload)."""
    execution = WorkflowExecution(
        execution_id=execution_id, site_id=site_id, source_event_id="evt-1"
    )
    result = create_parchi_for_worker(
        parchi_id=f"parchi-{execution_id}-{worker_id}",
        execution=execution,
        worker=RosterEntry(worker_id=worker_id, display_name="Worker"),
        provenance=ParchiProvenance(stage=None, reading=None),
        idempotency_key=execution.idempotency_key_for(worker_id),
        now=NOW,
        store=stores["store"],
        tokens=stores["tokens"],
    )
    return result.parchi, result.qr.payload


# ---------------------------------------------------------------------------
# 1 & 2 -- supervisor halts their own site, and only their own site
# ---------------------------------------------------------------------------


def test_1_supervisor_issues_halt_for_an_assigned_site(service):
    decision = service.require_issue_halt(principal=SUPERVISOR, site_id=SITE, now=NOW)
    assert decision.allowed is True


def test_2_supervisor_issues_halt_for_an_unrelated_site(service):
    with pytest.raises(AuthorizationDenied):
        service.require_issue_halt(principal=SUPERVISOR, site_id=OTHER_SITE, now=NOW)


def test_2b_another_supervisors_site_is_unrelated_to_this_one(service):
    """Cross-site supervisor access, stated from the other direction."""
    with pytest.raises(AuthorizationDenied):
        service.require_issue_halt(principal=OTHER_SUPERVISOR, site_id=SITE, now=NOW)


# ---------------------------------------------------------------------------
# 3 & 4 -- the worker acknowledges their own parchi, and not another's
# ---------------------------------------------------------------------------


def test_3_worker_acknowledges_their_own_parchi(service, stores):
    parchi, payload = _open_parchi(stores, worker_id="wrk-1")
    outcome = service.acknowledge_own_parchi(principal=WORKER_A, payload=payload, now=NOW, **stores)
    assert outcome.parchi.acknowledged_by == "wrk-1"
    assert outcome.parchi.parchi_id == parchi.parchi_id


def test_4_a_worker_cannot_acknowledge_another_workers_parchi(service, stores):
    """Worker B holds a perfectly valid link for worker A's parchi, from the same site."""
    _, payload = _open_parchi(stores, worker_id="wrk-1", site_id=SITE)
    with pytest.raises(AuthorizationDenied):
        service.acknowledge_own_parchi(principal=WORKER_B, payload=payload, now=NOW, **stores)


# ---------------------------------------------------------------------------
# 5 -- the deliberate asymmetry: the supervisor cannot finish it for them
# ---------------------------------------------------------------------------


def test_5_supervisor_cannot_acknowledge_the_workers_parchi(service, stores):
    """The supervisor created the workflow, issued the halt, manages the site, and knows the
    worker. The parchi stops anyway, and stays unacknowledged."""
    parchi, payload = _open_parchi(stores, worker_id="wrk-1", site_id=SITE)
    with pytest.raises(AuthorizationDenied) as denied:
        service.acknowledge_own_parchi(principal=SUPERVISOR, payload=payload, now=NOW, **stores)
    assert denied.value.decision.policy_id == "no-proxy-acknowledgement"

    from aadesh_core.domain import ParchiState

    assert stores["store"].get(parchi.parchi_id).state is ParchiState.PENDING_ACK


# ---------------------------------------------------------------------------
# 6, 7, 8, 9 -- consent gates assistance, and stops gating when it lapses
# ---------------------------------------------------------------------------


def _consent(**overrides):
    fields = dict(
        context_id="ctx-1",
        parchi_id="parchi-1",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        granted_at=NOW,
        ttl=timedelta(hours=24),
        actor_worker_id="wrk-1",
    )
    fields.update(overrides)
    return grant_consent(**fields)


def test_6_facilitator_cannot_assist_without_consent(service):
    """A request naming the facilitator, before the worker agreed to anything."""
    requested = request_assistance(
        context_id="ctx-1",
        parchi_id="parchi-1",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        requested_at=NOW,
        ttl=timedelta(hours=24),
    )
    with pytest.raises(AuthorizationDenied):
        service.require_assist_claim(principal=FACILITATOR, consent=requested, now=NOW)


def test_7_worker_grants_consent_and_the_facilitator_may_assist(service):
    decision = service.require_assist_claim(principal=FACILITATOR, consent=_consent(), now=NOW)
    assert decision.allowed is True


def test_8_expired_consent_denies(service):
    with pytest.raises(AuthorizationDenied):
        service.require_assist_claim(
            principal=FACILITATOR, consent=_consent(), now=NOW + timedelta(days=2)
        )


def test_9_revoked_consent_denies(service):
    revoked = revoke_consent(_consent(), now=NOW + timedelta(hours=1))
    with pytest.raises(AuthorizationDenied):
        service.require_assist_claim(
            principal=FACILITATOR, consent=revoked, now=NOW + timedelta(hours=2)
        )


def test_9b_revoked_consent_denies_even_inside_its_original_window(service):
    """The consent had not lapsed. The worker withdrew it early, which must take effect
    immediately rather than at the expiry it would otherwise have had."""
    revoked = revoke_consent(_consent(), now=NOW + timedelta(minutes=5))
    assert revoked.expires_at > NOW + timedelta(minutes=10)
    with pytest.raises(AuthorizationDenied):
        service.require_assist_claim(
            principal=FACILITATOR, consent=revoked, now=NOW + timedelta(minutes=10)
        )


# ---------------------------------------------------------------------------
# 10 -- a facilitator can assist without being able to read the record
# ---------------------------------------------------------------------------


def test_10_facilitator_cannot_view_the_parchi(service, stores):
    parchi, _ = _open_parchi(stores, worker_id="wrk-1")
    with pytest.raises(AuthorizationDenied) as denied:
        service.require_view_parchi(principal=FACILITATOR, parchi=parchi, now=NOW)
    assert denied.value.decision.policy_id == "assist-is-not-disclosure"


def test_10b_assisting_does_not_open_the_record(service, stores):
    """The two decisions, one after the other, on the same facilitator: assist ALLOW,
    view DENY."""
    parchi, _ = _open_parchi(stores, worker_id="wrk-1")
    assert (
        service.require_assist_claim(principal=FACILITATOR, consent=_consent(), now=NOW).allowed
        is True
    )
    with pytest.raises(AuthorizationDenied):
        service.require_view_parchi(principal=FACILITATOR, parchi=parchi, now=NOW)


# ---------------------------------------------------------------------------
# 11 & 12 -- an unanswerable request and an unavailable engine both fail closed
# ---------------------------------------------------------------------------


def test_11_a_request_with_no_authorization_context_is_refused(cedar):
    from aadesh_core.authorization.resources import site_resource

    with pytest.raises(AuthorizationUnavailable):
        cedar.authorize(principal=SUPERVISOR, action="IssueHalt", resource=site_resource(SITE))


def test_12_an_unavailable_authorizer_permits_nothing(stores):
    unavailable = AuthorizationService(authz=_Unavailable())
    with pytest.raises(AuthorizationUnavailable):
        unavailable.require_issue_halt(principal=SUPERVISOR, site_id=SITE, now=NOW)


def test_12b_an_unavailable_authorizer_refuses_the_acknowledgement_too(stores):
    """Fail closed all the way through the protected operation: nothing is written."""
    parchi, payload = _open_parchi(stores, worker_id="wrk-1")
    unavailable = AuthorizationService(authz=_Unavailable())
    with pytest.raises(AuthorizationUnavailable):
        unavailable.acknowledge_own_parchi(principal=WORKER_A, payload=payload, now=NOW, **stores)

    from aadesh_core.domain import ParchiState

    assert stores["store"].get(parchi.parchi_id).state is ParchiState.PENDING_ACK


# ---------------------------------------------------------------------------
# 13 -- THE test: Cedar is not the only lock
# ---------------------------------------------------------------------------


def test_13_the_domain_still_refuses_when_the_authorizer_permits_everything(stores):
    """Replace the authorizer with one that ALLOWS EVERY ACTION, and the identity rule still
    holds.

    This is the test that proves Prompt 5's invariant did not get relocated into policy.
    `AllowAllTestOnly` is the most permissive component in the codebase; if a different
    worker could acknowledge on the strength of it, then every Cedar deny above would be
    load-bearing alone, and any future policy edit could quietly open the door.
    """
    parchi, payload = _open_parchi(stores, worker_id="wrk-1")
    permissive = AuthorizationService(authz=AllowAllTestOnly())

    # The authorization layer is satisfied -- it permits everything, by construction.
    assert permissive.require_view_parchi(principal=WORKER_B, parchi=parchi, now=NOW).allowed

    # The DOMAIN is not.
    with pytest.raises(WrongWorker):
        permissive.acknowledge_own_parchi(principal=WORKER_B, payload=payload, now=NOW, **stores)

    from aadesh_core.domain import ParchiState

    assert stores["store"].get(parchi.parchi_id).state is ParchiState.PENDING_ACK


def test_13b_the_domain_still_refuses_a_direct_bypass_of_the_boundary(stores):
    """The same guarantee with the boundary skipped entirely.

    `acknowledge_parchi` is the domain operation. Calling it directly -- which is what a
    future handler would do if it were written before this boundary existed -- still refuses
    a different worker, because the rule was never in the caller.
    """
    _, payload = _open_parchi(stores, worker_id="wrk-1")
    with pytest.raises(WrongWorker):
        acknowledge_parchi(
            payload=payload,
            actor_worker_id="wrk-2",
            now=NOW,
            store=stores["store"],
            tokens=stores["tokens"],
            ledger=stores["ledger"],
            audit=stores["audit"],
        )


def test_13c_a_supervisor_bypassing_the_boundary_is_refused_by_the_domain(stores):
    """Prompt 5's `WrongWorker`, reached through the raw domain call."""
    _, payload = _open_parchi(stores, worker_id="wrk-1")
    with pytest.raises(WrongWorker):
        acknowledge_parchi(
            payload=payload,
            actor_worker_id="sup-1",
            now=NOW,
            store=stores["store"],
            tokens=stores["tokens"],
            ledger=stores["ledger"],
            audit=stores["audit"],
        )


# ---------------------------------------------------------------------------
# The boundary does not replace the state machine
# ---------------------------------------------------------------------------


def test_cedar_does_not_own_the_state_machine(service, stores):
    """A sealed parchi is refused by the DOMAIN, not by a policy.

    The authorizer is asked and says yes -- the principal really is the worker named on the
    record -- and then the domain refuses the transition. If Cedar were gating on
    `resource.state`, the first assertion below would fail, and the authorization layer would
    have become a second state machine.
    """
    _, payload = _open_parchi(stores, worker_id="wrk-1")
    outcome = service.acknowledge_own_parchi(principal=WORKER_A, payload=payload, now=NOW, **stores)
    assert outcome.parchi.state.value == "acknowledged"

    # Asked directly, Cedar still permits: it answers a question about the principal, not
    # about whether the transition is legal.
    assert service.require_view_parchi(principal=WORKER_A, parchi=outcome.parchi, now=NOW).allowed

    # And the domain refuses the transition itself.
    from aadesh_core.parchi import acknowledge

    with pytest.raises(IllegalParchiTransition):
        acknowledge(outcome.parchi, actor_worker_id="wrk-1", now=NOW + timedelta(minutes=1))
