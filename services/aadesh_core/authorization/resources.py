"""Domain objects, translated into the entities Cedar evaluates against.

This module is the ONLY place the domain's shape meets Cedar's, and that is deliberate. Two
properties depend on there being one seam:

  * **Time is converted once.** The domain carries timezone-aware datetimes; Cedar compares
    `Long`s. `to_epoch_seconds` is the single conversion, and it refuses a naive datetime
    rather than assuming a zone. Assuming UTC for a naive `datetime(2026, 10, 8, 9, 0)` read
    in IST would move a consent window by five and a half hours -- silently, and in whichever
    direction happened to hide the bug.

  * **No personal data crosses over.** A Cedar entity store is logged, snapshotted and read
    by policy authors. Everything built here is an id, a state, a site or an instant. The
    worker appears as `EntityRef("Principal", worker_id)` and nothing else, so there is no
    name, phone number or identity document in the store to leak.

Attribute names here are camelCase to match `infra/cedar/schema.cedarschema.json`. The two
must move together; `tests/unit/test_cedar_authorization_model.py` evaluates real policies
against these shapes, so a mismatch is a failing test rather than a silently denied request.
"""

from __future__ import annotations

from datetime import datetime

from aadesh_core.consent import ClaimAssistanceContext
from aadesh_core.parchi import Parchi
from aadesh_core.ports.authz import AuthzResource, EntityRef

WORKER_ENTITY = "Worker"
PRINCIPAL_ENTITY = "Principal"
PARCHI_ENTITY = "Parchi"
EXECUTION_ENTITY = "StandingOrderExecution"


def to_epoch_seconds(moment: datetime) -> int:
    """An instant, as the integer Cedar compares.

    Refuses a naive datetime. `datetime.timestamp()` on a naive value silently interprets it
    in the host's local zone, so on a developer's laptop in IST and a Lambda in UTC the same
    consent would expire at two different instants. That is a security bug that only shows up
    in one of the two places.
    """
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(
            f"{moment!r} has no timezone, so it is not an instant. Attach one (e.g. "
            f"tzinfo=UTC) rather than letting the host's local zone decide what this means."
        )
    return int(moment.timestamp())


def site_resource(site_id: str) -> AuthzResource:
    """The resource for a site-scoped action such as IssueHalt or ViewSiteExecution."""
    return AuthzResource(entity_type="Site", entity_id=site_id, attributes={"siteId": site_id})


def parchi_resource(parchi: Parchi) -> AuthzResource:
    """A parchi as the authorization layer sees it.

    `worker` is an ENTITY REFERENCE, not a string. That is what lets the identity rule be
    `resource.worker == principal` -- entity equality, which a caller cannot satisfy by
    supplying a plausible-looking id.

    `state` is carried so a decision can be reported alongside the state it was made in, but
    **no policy reads it**. Whether PENDING_ACK may become ACKNOWLEDGED is the domain's
    decision, made in `aadesh_core.parchi`; enforcing it here too would create a second state
    machine that would eventually disagree with the first.

    `execution` is omitted entirely when the parchi has no workflow execution, rather than
    being set to a placeholder. A parchi opened by hand genuinely has none, and an invented
    execution id would be a fabricated provenance claim.
    """
    attributes: dict[str, object] = {
        "worker": EntityRef(PRINCIPAL_ENTITY, parchi.worker_id),
        "siteId": parchi.site_id,
        "state": parchi.state.value,
    }
    if parchi.workflow_execution_id is not None:
        attributes["execution"] = EntityRef(EXECUTION_ENTITY, parchi.workflow_execution_id)

    return AuthzResource(
        entity_type=PARCHI_ENTITY, entity_id=parchi.parchi_id, attributes=attributes
    )


def claim_assistance_resource(consent: ClaimAssistanceContext) -> AuthzResource:
    """A consent, as the resource an AssistClaim is requested against.

    AssistClaim is authorized against THIS, never against a Parchi. That is the structural
    half of "a facilitator cannot read the record": a facilitator holding only a parchi
    reference has no resource on which to name an assist request at all, so there is nothing
    for a permissive policy to accidentally match.

    `revokedAt` is omitted when there was no revocation rather than set to 0 or to the expiry.
    A present-but-sentinel value would be a revocation instant that never happened, and the
    policy tests that for existence.
    """
    attributes: dict[str, object] = {
        "worker": EntityRef(WORKER_ENTITY, consent.worker_id),
        "facilitator": EntityRef(PRINCIPAL_ENTITY, consent.facilitator_id),
        "parchi": EntityRef(PARCHI_ENTITY, consent.parchi_id),
        "consentGranted": consent.consent_granted,
        "grantedAt": to_epoch_seconds(consent.granted_at),
        "expiresAt": to_epoch_seconds(consent.expires_at),
    }
    if consent.revoked_at is not None:
        attributes["revokedAt"] = to_epoch_seconds(consent.revoked_at)

    return AuthzResource(
        entity_type="ClaimAssistanceContext",
        entity_id=consent.context_id,
        attributes=attributes,
    )
