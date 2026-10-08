"""Shared builders for authorization tests.

Authorization tests are written at the level of **principals, actions and resources**,
because that is the vocabulary Cedar speaks and the vocabulary a reviewer needs in order
to check a rule by reading it. Building those by hand in every file invites the two
failure modes that matter here: a helper that quietly defaults a security-relevant
attribute (so a test passes for the wrong reason), and helpers that drift between files
(so two tests disagree about what a "normal" parchi is).

So every attribute is explicit and required, and the two genuinely universal facts --
a parchi is pending, a claim context is live -- are stated rather than defaulted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aadesh_core.domain import Principal
from aadesh_core.parchi import Parchi, issue, open_parchi
from aadesh_core.ports.authz import AuthzResource, EntityRef

#: A fixed instant. Authorization tests that involve consent must state WHEN the request is
#: being decided, because expiry is a policy condition rather than a computed fact.
FIXED_NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)

# Roles as they appear in the Cedar principal entity. Kept as constants so a typo in a
# test is a NameError rather than a test that silently probes the wrong role.
SUPERVISOR = "supervisor"
WORKER = "worker"
FACILITATOR = "facilitator"


def supervisor(principal_id: str = "sup-1", *, site: str | None = "site-001") -> Principal:
    """A supervisor. `site=None` models the rogue case: a role claim with no assignment."""
    return Principal(principal_id=principal_id, role=SUPERVISOR, assigned_site=site)


def worker(principal_id: str = "wrk-1", *, site: str | None = None) -> Principal:
    """A worker. Cedar does not need the site on the principal -- the Parchi carries the
    worker entity, and the domain owns rostering -- so it defaults to None."""
    return Principal(principal_id=principal_id, role=WORKER, assigned_site=site)


def facilitator(principal_id: str = "fac-1") -> Principal:
    return Principal(principal_id=principal_id, role=FACILITATOR, assigned_site=None)


def site_resource(site_id: str = "site-001") -> AuthzResource:
    return AuthzResource(entity_type="Site", entity_id=site_id, attributes={"siteId": site_id})


def parchi_resource(
    *,
    parchi_id: str = "parchi-001",
    worker_id: str = "wrk-1",
    site_id: str = "site-001",
    state: str = "pending_ack",
    execution_id: str | None = "exec-1",
) -> AuthzResource:
    """A Parchi as Cedar sees it.

    `worker` is a reference to the acting principal entity, not a string. That is what lets
    the identity rule be `resource.worker == principal` -- entity equality, which cannot be
    satisfied by forging an id string.
    """
    attributes: dict[str, Any] = {
        "worker": EntityRef("Principal", worker_id),
        "siteId": site_id,
        "state": state,
    }
    if execution_id is not None:
        attributes["execution"] = EntityRef("StandingOrderExecution", execution_id)
    return AuthzResource(entity_type="Parchi", entity_id=parchi_id, attributes=attributes)


def claim_context_resource(
    *,
    context_id: str = "ctx-1",
    worker_id: str = "wrk-1",
    facilitator_id: str = "fac-1",
    parchi_id: str = "parchi-001",
    consent_granted: bool = True,
    granted_at: int = 1_000,
    expires_at: int = 2_000,
    revoked_at: int | None = None,
) -> AuthzResource:
    """A ClaimAssistanceContext as Cedar sees it.

    Times are epoch SECONDS, not datetimes. Cedar has no clock and no datetime type in core;
    passing integers and comparing them in the policy is what keeps the expiry decision
    inside the policy rather than in Python next to it.
    """
    attributes: dict[str, Any] = {
        "worker": EntityRef("Worker", worker_id),
        "facilitator": EntityRef("Principal", facilitator_id),
        "parchi": EntityRef("Parchi", parchi_id),
        "consentGranted": consent_granted,
        "grantedAt": granted_at,
        "expiresAt": expires_at,
    }
    if revoked_at is not None:
        attributes["revokedAt"] = revoked_at
    return AuthzResource(
        entity_type="ClaimAssistanceContext", entity_id=context_id, attributes=attributes
    )


def parchi_domain(
    *,
    parchi_id: str = "parchi-001",
    worker_id: str = "wrk-1",
    site_id: str = "site-001",
    execution_id: str | None = "exec-1",
    now: datetime = FIXED_NOW,
) -> Parchi:
    """A real domain `Parchi` in PENDING_ACK, for tests that exercise the resource BUILDER
    rather than Cedar directly. Built through the domain's own constructors so a change to
    the parchi shape surfaces here instead of in a hand-rolled stand-in."""
    return issue(
        open_parchi(
            parchi_id=parchi_id,
            site_id=site_id,
            worker_id=worker_id,
            stage=None,
            reading=None,
            obligation_ids=(),
            entitlement_refs=(),
            readiness_checklist=(),
            displaced_worker_days=1,
            now=now,
            workflow_execution_id=execution_id,
        ),
        now=now,
    )
