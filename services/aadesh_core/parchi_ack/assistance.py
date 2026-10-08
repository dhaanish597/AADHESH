"""Facilitator assistance: the minimal view a facilitator gets when a worker opts in.

A facilitator helping with a claim sees ONLY what is necessary to assist. They do NOT see:

- the complete Parchi
- worker phone
- Aadhaar
- address
- bank account
- PAN
- raw QR token
- unnecessary personal information

This is enforced at multiple layers:
1. Cedar policy: ViewParchi is forbidden for facilitators
2. Domain: assist_claim returns a minimal view, not the full parchi
3. Tests: verify the response contains none of the banned personal data

The assistance context ID is how a facilitator's action is correlated with the worker's
consent. It is opaque -- knowing it does not grant access to the parchi.
"""

from __future__ import annotations

from dataclasses import dataclass

from aadesh_core.consent import ClaimAssistanceContext
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack.events import AssistClaim
from aadesh_core.ports.audit import AuditLog


@dataclass(frozen=True, slots=True)
class FacilitatorClaimView:
    """The minimal information a facilitator needs to assist with a claim.

    This is deliberately thin. Every field here is either an id, a state, or an instant --
    nothing personal, nothing that would be a problem if it appeared in an audit log.

    A facilitator who holds this view still cannot read the worker's full Parchi. That
    boundary is enforced by Cedar (ViewParchi is forbidden) and by the domain (this view
    is what the operation returns, not the parchi itself).
    """

    context_id: str
    """The consent context this assistance is under. Used to correlate facilitator actions
    with the worker's consent record."""

    parchi_id: str
    """A reference to the parchi being assisted with. This is NOT the full parchi -- it is
    just an identifier, like a case number."""

    worker_id: str
    """The worker being assisted. Present because the facilitator needs to know WHO they are
    helping. This is the minimum: an id, not a name or contact detail."""

    site_id: str
    """The site the claim relates to. Needed for context."""

    claim_status: str
    """The current status of the claim/parchi. One of: pending_ack, acknowledged, sealed, void.
    Enough for a facilitator to know where things stand without seeing the full record."""

    consent_status: str
    """Whether the worker's consent is active. One of: granted, expired, revoked, not_granted.
    Lets the facilitator know if they can still assist."""

    consent_granted_at: str
    """When the worker opted in (ISO format). Needed to know how long assistance has been
    available."""

    consent_expires_at: str
    """When the consent lapses (ISO format). So the facilitator knows if they need to ask
    again."""

    created_at: str
    """When this assistance context was created (ISO format)."""


def build_facilitator_view(
    *,
    consent: ClaimAssistanceContext,
    parchi: Parchi,
) -> FacilitatorClaimView:
    """Build the minimal facilitator view from a consent and its parchi.

    This function is PURE: it builds a view from data, it does not authorize, it does not
    write, it does not check clocks. Authorization happens BEFORE this is called (Cedar
    decides if the facilitator may AssistClaim), and the view is what the operation returns.

    The view contains NONE of:
    - raw QR token
    - phone number
    - Aadhaar
    - bank account
    - PAN
    - address
    - full Parchi contents (obligations, entitlements, readings, etc.)
    """

    # Determine claim status from parchi state -- enough for a facilitator to know
    # where things stand without seeing the full record.
    claim_status = parchi.state.value

    # Determine consent status from the consent record
    if consent.revoked_at is not None:
        consent_status = "revoked"
    elif consent.expires_at <= consent.granted_at:
        # Should not happen due to validation, but defend anyway
        consent_status = "expired"
    else:
        consent_status = "granted"

    return FacilitatorClaimView(
        context_id=consent.context_id,
        parchi_id=consent.parchi_id,
        worker_id=consent.worker_id,
        site_id=parchi.site_id,
        claim_status=claim_status,
        consent_status=consent_status,
        consent_granted_at=consent.granted_at.isoformat(),
        consent_expires_at=consent.expires_at.isoformat(),
        created_at=consent.granted_at.isoformat(),
    )


def assist_claim(
    *,
    consent: ClaimAssistanceContext,
    parchi: Parchi,
    facilitator_id: str,
    now,
    audit: AuditLog,
    event_id: str | None = None,
) -> FacilitatorClaimView:
    """Assist with a claim, returning only the minimal facilitator view.

    This is the DOMAIN OPERATION for AssistClaim. It is called AFTER Cedar has authorized
    the facilitator to perform this action against the consent context.

    The operation:
    1. Builds the minimal facilitator view
    2. Records an audit event (no personal data, no credentials)

    It does NOT:
    - Return the full Parchi
    - Return any worker personal details
    - Return any credentials
    - Grant ViewParchi or any other permission

    Args:
        consent: The ClaimAssistanceContext the facilitator is authorized against.
        parchi: The parchi being assisted with (used only for status/site info).
        facilitator_id: The facilitator performing the assistance.
        now: The current time.
        audit: The audit log to record the assistance event.
        event_id: Optional event ID for the audit record.

    Returns:
        A FacilitatorClaimView with only the minimal information needed to assist.
    """
    view = build_facilitator_view(consent=consent, parchi=parchi)

    # Record the audit event -- no personal data, no credentials
    event = AssistClaim(
        event_id=event_id or f"evt-assist-{consent.context_id}",
        context_id=consent.context_id,
        parchi_id=consent.parchi_id,
        worker_id=consent.worker_id,
        facilitator_id=facilitator_id,
        assisted_at=now,
    )
    audit.record(event=event.event_type, detail=event.as_audit_detail())

    return view
