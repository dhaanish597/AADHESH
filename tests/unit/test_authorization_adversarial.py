"""Adversarial cases: requests that are not the shape they claim to be.

The happy-path suite proves the rules work. This one proves that breaking the REQUEST does not
break the boundary -- because every case below is something a caller can actually produce. A
handler that builds a principal from a session with a null role, a resource from a lookup that
returned nothing, an action name from a request path: all of those arrive here, and none of
them may end in "permitted".

The split this file keeps insisting on:

  * **Not answerable -> `AuthorizationUnavailable`.** A blank principal, an action the schema
    never declared, a request with no instant. The request was malformed; retrying it unchanged
    will not help, and it must not be reported as "you are not allowed".
  * **Answerable, and the answer is no -> `AuthorizationDenied`.** A supervisor with no site, a
    worker reaching for an action that is not theirs. These are ordinary refusals.

Both fail closed. The distinction is about what the caller is told, not about what is allowed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_core.authorization.resources import parchi_resource as parchi_from_domain
from aadesh_core.authorization.service import AuthorizationService
from aadesh_core.domain import Principal
from aadesh_core.errors import AuthorizationDenied, AuthorizationUnavailable
from aadesh_core.ports.authz import AuthzResource, EntityRef
from tests.support.authz_builders import (
    claim_context_resource,
    facilitator,
    parchi_domain,
    parchi_resource,
    site_resource,
    supervisor,
    worker,
)

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
EPOCH = int(NOW.timestamp())

SUPERVISOR = supervisor("sup-1", site="site-001")
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


def ask(cedar, *, principal, action, resource, context=None):
    return cedar.authorize(principal=principal, action=action, resource=resource, context=context)


def deny(cedar, *, principal, action, resource, context=None) -> str | None:
    """Ask, require a refusal, and return the policy that made it (None for an implicit one)."""
    decision = ask(cedar, principal=principal, action=action, resource=resource, context=context)
    assert decision.allowed is False
    return decision.policy_id


# ---------------------------------------------------------------------------
# Malformed principals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("principal", ["sup-1", None, 42, object()])
def test_a_principal_that_is_not_a_principal_is_unanswerable(cedar, principal):
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=principal,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )


@pytest.mark.parametrize("principal_id", ["", "   ", "\t"])
def test_a_principal_with_no_id_is_unanswerable(cedar, principal_id):
    blank = Principal(principal_id=principal_id, role="supervisor", assigned_site="site-001")
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=blank,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )


@pytest.mark.parametrize("role", ["", "   "])
def test_a_principal_with_no_role_is_unanswerable(cedar, role):
    """A session whose role claim did not survive deserialization. Not a denial -- there is
    nobody here to deny."""
    nameless = Principal(principal_id="sup-1", role=role, assigned_site="site-001")
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=nameless,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )


def test_an_invented_role_is_denied_rather_than_rejected(cedar):
    """`role: "admin"` is well-formed, so it is ANSWERABLE -- and the answer is no.

    This is the case that matters for "do not create a generic admin". A role the schema has
    never heard of gets no special treatment: it matches no permit, and the denies that do not
    name a role still hold."""
    admin = Principal(principal_id="root", role="admin", assigned_site="site-001")
    assert (
        deny(
            cedar,
            principal=admin,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )
        is None
    )
    assert (
        deny(
            cedar,
            principal=admin,
            action="ViewParchi",
            resource=parchi_resource(worker_id="wrk-1"),
            context={"now": EPOCH},
        )
        is None
    )


# ---------------------------------------------------------------------------
# Malformed actions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["", "   ", None])
def test_an_empty_action_is_unanswerable(cedar, action):
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action=action,
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )


@pytest.mark.parametrize("action", ["IssueHalt_all", "DeleteParchi", "issuehalt", "Admin"])
def test_an_action_the_schema_never_declared_is_unanswerable(cedar, action):
    """Checked against the schema, not against a list retyped into the adapter -- so an action
    added to the policy file without a schema entry is refused rather than half-supported."""
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action=action,
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )


# ---------------------------------------------------------------------------
# Malformed resources
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("resource", ["site-001", None, {"entity_type": "Site"}, 7])
def test_a_resource_that_is_not_a_resource_is_unanswerable(cedar, resource):
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action="IssueHalt",
            resource=resource,
            context={"now": EPOCH},
        )


@pytest.mark.parametrize("entity_id", ["", "   "])
def test_a_resource_with_no_id_is_unanswerable(cedar, entity_id):
    empty = AuthzResource(entity_type="Site", entity_id=entity_id, attributes={})
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action="IssueHalt",
            resource=empty,
            context={"now": EPOCH},
        )


@pytest.mark.parametrize("entity_type", ["Sitte", "site", "Parchis", "Action", ""])
def test_an_unknown_resource_type_is_unanswerable(cedar, entity_type):
    """A handler that looked up the wrong table. Cedar would deny it anyway; refusing it here
    keeps "no such kind of thing" from being reported as "you may not touch this thing"."""
    mystery = AuthzResource(entity_type=entity_type, entity_id="x-1", attributes={})
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action="IssueHalt",
            resource=mystery,
            context={"now": EPOCH},
        )


def test_a_resource_carrying_something_cedar_cannot_serialise_is_unanswerable(cedar):
    """Policy evaluation failure, reached through the entity store. A caller who smuggled a
    live object into an attribute gets an outage, not a decision."""
    poisoned = AuthzResource(
        entity_type="Site", entity_id="site-001", attributes={"siteId": object()}
    )
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action="IssueHalt",
            resource=poisoned,
            context={"now": EPOCH},
        )


# ---------------------------------------------------------------------------
# Missing request context
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("context", [None, {}, {"now": None}, {"now": "1700000000"}])
def test_a_request_without_an_instant_is_unanswerable(cedar, context):
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context=context,
        )


@pytest.mark.parametrize("now", [True, False])
def test_a_boolean_is_not_an_instant(cedar, now):
    """`True` is an `int` in Python. Accepted silently it would put the epoch at 1970 and make
    every unexpired consent read as long expired."""
    with pytest.raises(AuthorizationUnavailable):
        ask(
            cedar,
            principal=SUPERVISOR,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": now},
        )


# ---------------------------------------------------------------------------
# Assignments that are missing rather than malformed
# ---------------------------------------------------------------------------


def test_a_supervisor_with_no_site_assignment_is_denied(cedar):
    """The role is intact; the assignment is not. This is the rogue case the whole
    "do not rely solely on role" requirement is about."""
    unassigned = supervisor("sup-9", site=None)
    assert (
        deny(
            cedar,
            principal=unassigned,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_parchi_naming_no_worker_is_denied(cedar):
    """A malformed parchi record -- one that never got a worker attached. The identity permit
    cannot fire, so nothing is allowed."""
    widowed = AuthzResource(
        entity_type="Parchi",
        entity_id="parchi-orphan",
        attributes={"siteId": "site-001", "state": "pending_ack"},
    )
    assert (
        deny(
            cedar,
            principal=WORKER_A,
            action="AcknowledgeOwnParchi",
            resource=widowed,
            context={"now": EPOCH},
        )
        is None
    )


# ---------------------------------------------------------------------------
# Role confusion
# ---------------------------------------------------------------------------


def test_a_worker_cannot_issue_a_halt(cedar):
    assert (
        deny(
            cedar,
            principal=worker("wrk-1", site="site-001"),
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_facilitator_cannot_issue_a_halt(cedar):
    assert (
        deny(
            cedar,
            principal=FACILITATOR,
            action="IssueHalt",
            resource=site_resource("site-001"),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_supervisor_cannot_assist_a_claim(cedar):
    """AssistClaim is a facilitator's action. A supervisor holding a live consent still cannot
    take it -- the permit names the role, and the deny closes the rest."""
    assert (
        deny(
            cedar,
            principal=SUPERVISOR,
            action="AssistClaim",
            resource=claim_context_resource(
                facilitator_id="sup-1", granted_at=EPOCH - 10, expires_at=EPOCH + 10_000
            ),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_worker_cannot_assist_a_claim_against_their_own_consent(cedar):
    assert (
        deny(
            cedar,
            principal=WORKER_A,
            action="AssistClaim",
            resource=claim_context_resource(
                worker_id="wrk-1",
                facilitator_id="fac-1",
                granted_at=EPOCH - 10,
                expires_at=EPOCH + 10_000,
            ),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_facilitator_named_on_someone_elses_consent_cannot_assist(cedar):
    """A live, unrevoked, unexpired consent -- naming a different facilitator."""
    assert (
        deny(
            cedar,
            principal=FACILITATOR,
            action="AssistClaim",
            resource=claim_context_resource(
                facilitator_id="fac-OTHER", granted_at=EPOCH - 10, expires_at=EPOCH + 10_000
            ),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_supervisor_cannot_view_a_parchi_on_a_site_they_do_not_hold(cedar):
    """Cross-site read. The supervisor's scope is a site, and this record is not on it."""
    assert (
        deny(
            cedar,
            principal=SUPERVISOR,
            action="ViewParchi",
            resource=parchi_resource(worker_id="wrk-1", site_id="site-999"),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_supervisor_can_view_a_parchi_on_their_own_site(cedar):
    """The control for the case above: the same request, on the assigned site, is permitted.
    Without this, the previous test would pass just as happily if ViewParchi were broken."""
    decision = ask(
        cedar,
        principal=SUPERVISOR,
        action="ViewParchi",
        resource=parchi_resource(worker_id="wrk-1", site_id="site-001"),
        context={"now": EPOCH},
    )
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# The boundary refuses malformed requests too, not only the adapter
# ---------------------------------------------------------------------------


def test_the_service_refuses_a_principal_it_cannot_name(service):
    """The gate must not be more trusting than the engine behind it."""
    nameless = Principal(principal_id="", role="supervisor", assigned_site="site-001")
    with pytest.raises(AuthorizationUnavailable):
        service.require_issue_halt(principal=nameless, site_id="site-001", now=NOW)


def test_the_service_refuses_a_naive_instant(service):
    """A caller that forgot a timezone. `to_epoch_seconds` refuses rather than letting the
    host's local zone decide when a consent expires."""
    with pytest.raises(ValueError, match="timezone"):
        service.require_issue_halt(
            principal=SUPERVISOR, site_id="site-001", now=datetime(2026, 10, 8, 9, 0)
        )


def test_a_denial_does_not_leak_its_reason_to_the_caller(service):
    """`AuthorizationDenied` carries the decision for logs and tests, and one identical
    sentence for everyone else. A caller who could read the policy id apart would have a probe
    for which records exist."""
    with pytest.raises(AuthorizationDenied) as denied:
        service.require_issue_halt(principal=SUPERVISOR, site_id="site-999", now=NOW)
    assert denied.value.decision.policy_id is None  # implicit denial: nothing permitted it
    assert str(denied.value) == "You do not have permission to perform this action."
    assert "site-999" not in str(denied.value)
    assert "sup-1" not in str(denied.value)


def test_two_different_refusals_are_indistinguishable_to_the_caller(service, cedar):
    """Cross-site halt and a role that has no business here produce the SAME sentence."""
    sentences = set()
    for principal, site in ((SUPERVISOR, "site-999"), (facilitator("fac-1"), "site-001")):
        with pytest.raises(AuthorizationDenied) as denied:
            service.require_issue_halt(principal=principal, site_id=site, now=NOW)
        sentences.add(str(denied.value))
    assert len(sentences) == 1


# ---------------------------------------------------------------------------
# Cedar itself being unavailable
# ---------------------------------------------------------------------------


def test_a_missing_policy_file_is_an_outage_not_a_crash(tmp_path: Path):
    """Fail closed at the point of construction. A boundary that cannot load its policy set
    must not be built at all -- raising `AuthorizationUnavailable` makes that an outage the
    caller can handle, rather than a `FileNotFoundError` nobody expects."""
    with pytest.raises(AuthorizationUnavailable):
        CedarAuthorizationProvider(
            policy_path=tmp_path / "absent.cedar",
            denials_path=tmp_path / "absent.json",
        )


def test_a_missing_denials_file_is_an_outage(tmp_path: Path, repo_root):
    with pytest.raises(AuthorizationUnavailable):
        CedarAuthorizationProvider(
            policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
            denials_path=tmp_path / "absent.json",
        )


def test_a_syntactically_broken_policy_set_is_an_outage(tmp_path: Path, repo_root):
    """Policy evaluation failure at load. Half a policy set is worse than none: the forbids
    that fail to parse are exactly the ones nobody would notice were missing."""
    broken = tmp_path / "broken.cedar"
    broken.write_text(
        "permit (principal, action, resource) when { this is not cedar", encoding="utf-8"
    )
    with pytest.raises(AuthorizationUnavailable):
        CedarAuthorizationProvider(
            policy_path=broken,
            denials_path=repo_root / "infra" / "cedar" / "denials.json",
        )


def test_an_unreadable_denials_file_is_an_outage(tmp_path: Path, repo_root):
    """Refusing to start is right here too. Falling back to a default sentence would mean a
    denial displayed without the sentence the policy author wrote for it."""
    malformed = tmp_path / "denials.json"
    malformed.write_text("{not json at all", encoding="utf-8")
    with pytest.raises(AuthorizationUnavailable):
        CedarAuthorizationProvider(
            policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
            denials_path=malformed,
        )


def test_a_policy_set_that_fails_schema_validation_is_reported(cedar):
    """`validate()` is the other half: policies that PARSE but do not typecheck against the
    schema. It is exercised here so a future edit that breaks the schema linkage fails a test
    rather than silently denying every request in production."""
    assert cedar.validate() == []


# ---------------------------------------------------------------------------
# Worker A reaching for worker B's record, from every direction
# ---------------------------------------------------------------------------


def test_worker_a_cannot_acknowledge_worker_bs_parchi(cedar):
    assert (
        deny(
            cedar,
            principal=WORKER_A,
            action="AcknowledgeOwnParchi",
            resource=parchi_resource(worker_id="wrk-2"),
            context={"now": EPOCH},
        )
        == "no-proxy-acknowledgement"
    )


def test_worker_a_cannot_view_worker_bs_parchi(cedar):
    assert (
        deny(
            cedar,
            principal=WORKER_A,
            action="ViewParchi",
            resource=parchi_resource(worker_id="wrk-2"),
            context={"now": EPOCH},
        )
        is None
    )


def test_a_worker_cannot_escape_their_own_record_by_claiming_a_role(cedar):
    """The same person, wearing a supervisor's role badge, reaching for a worker's parchi.
    The forbid names the action rather than a role, so the badge changes nothing."""
    disguised = Principal(principal_id="wrk-1", role="supervisor", assigned_site="site-001")
    assert (
        deny(
            cedar,
            principal=disguised,
            action="AcknowledgeOwnParchi",
            resource=parchi_resource(worker_id="wrk-2", site_id="site-001"),
            context={"now": EPOCH},
        )
        == "no-proxy-acknowledgement"
    )


def test_a_real_parchi_from_the_domain_is_denied_to_the_wrong_worker(cedar):
    """End to end through the domain's own constructor, so the resource under test is the real
    shape rather than a builder's approximation of it."""
    record = parchi_domain(parchi_id="parchi-real", worker_id="wrk-1", site_id="site-001")
    assert (
        deny(
            cedar,
            principal=WORKER_B,
            action="AcknowledgeOwnParchi",
            resource=parchi_from_domain(record),
            context={"now": EPOCH},
        )
        == "no-proxy-acknowledgement"
    )


def test_the_entity_store_carries_no_personal_data_for_any_of_these_requests(cedar):
    """A last sweep across every resource this file builds: nothing but ids, states and
    instants ever reaches the engine."""
    from aadesh_adapters.authz.cedar_authz import _uid

    forbidden = {"name", "display_name", "phone", "aadhaar", "address", "pan", "bank", "account"}
    resources = [
        site_resource("site-001"),
        parchi_resource(worker_id="wrk-1"),
        claim_context_resource(),
    ]
    for resource in resources:
        for key, value in resource.attributes.items():
            assert key.lower() not in forbidden
            if not isinstance(value, EntityRef):
                assert isinstance(value, (str, int, float, bool)), (key, value)
        assert _uid(resource.entity_type, resource.entity_id)["type"].startswith("Aadesh::")
