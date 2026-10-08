"""The audit events for parchi acknowledgement, sealing, and consent lifecycle.

Every event here is deliberately thin, because it is also the record that gets shipped to a
log sink and kept forever. The test each has to pass is the same one the QR passes: everything
in here must be safe to leave lying around -- no raw tokens, no contact details, no identity
documents.

So there is no `token` field. There IS a `token_reference`, which is `tok_` plus the first 16
hex characters of the token's SHA-256 -- enough to correlate "which link was used" across
audit lines, useless for replaying it. `tests/unit/test_parchi_privacy.py` walks the event's
serialised form looking for the raw token, and fails if it is anywhere.

The consent events (Prompt 7) follow the same rule: they record WHO granted/revoked/assisted,
for WHICH resource, to WHICH facilitator, and WHEN -- but never the worker's personal details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aadesh_core.domain import AcknowledgementMethod

PARCHI_EVENT_SCHEMA_VERSION = "parchi-event/1"
"""Stamped on every event so a consumer can tell which shape of record it is reading."""

EVENT_TYPE_PARCHI_ACKNOWLEDGED = "ParchiAcknowledged"
EVENT_TYPE_PARCHI_SEALED = "ParchiSealed"
EVENT_TYPE_CONSENT_GRANTED = "ConsentGranted"
EVENT_TYPE_CONSENT_REVOKED = "ConsentRevoked"
EVENT_TYPE_ASSIST_CLAIM = "AssistClaim"


@dataclass(frozen=True, slots=True)
class ParchiAcknowledged:
    """One worker's explicit confirmation of one parchi.

    `worker_id` appears here and is the only personal field. It is the minimum needed to
    prove WHO confirmed: an audit line saying "somebody confirmed parchi-001" would not
    support the claim the record exists to make.
    """

    event_id: str
    parchi_id: str
    worker_id: str
    occurred_at: datetime
    acknowledgement_method: AcknowledgementMethod
    token_reference: str
    workflow_execution_id: str | None = None
    site_id: str | None = None
    schema_version: str = PARCHI_EVENT_SCHEMA_VERSION
    event_type: str = field(default=EVENT_TYPE_PARCHI_ACKNOWLEDGED)

    def as_audit_detail(self) -> dict[str, str]:
        """The mapping handed to the `AuditLog` port.

        Flat strings only, and every value is either an id or an instant -- there is no field
        here a raw token could be smuggled into.
        """
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "parchi_id": self.parchi_id,
            "site_id": self.site_id or "",
            "workflow_execution_id": self.workflow_execution_id or "",
            "worker_id": self.worker_id,
            "occurred_at": self.occurred_at.isoformat(),
            "acknowledgement_method": self.acknowledgement_method.value,
            "token_reference": self.token_reference,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ParchiSealed:
    """The record frozen over its content hash.

    Kept separate from `ParchiAcknowledged` because they are different facts about different
    actors: the worker confirmed, the system froze. A trail that merged them could not answer
    "did the worker confirm this, or did a supervisor seal it without them?".
    """

    event_id: str
    parchi_id: str
    site_id: str
    worker_id: str
    occurred_at: datetime
    content_hash: str
    schema_version: str = PARCHI_EVENT_SCHEMA_VERSION
    event_type: str = field(default=EVENT_TYPE_PARCHI_SEALED)

    def as_audit_detail(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "parchi_id": self.parchi_id,
            "site_id": self.site_id,
            "worker_id": self.worker_id,
            "occurred_at": self.occurred_at.isoformat(),
            "content_hash": self.content_hash,
            "schema_version": self.schema_version,
        }


# ---------------------------------------------------------------------------
# Consent lifecycle events (Prompt 7)
# ---------------------------------------------------------------------------


CONSENT_EVENT_SCHEMA_VERSION = "consent-event/1"


@dataclass(frozen=True, slots=True)
class ConsentGranted:
    """One worker granted one facilitator permission to assist with one claim.

    Records the fact of consent. Does NOT record any personal details about the worker --
    the worker_id is the minimum needed to prove who opted in, and nothing more.
    """

    event_id: str
    context_id: str
    parchi_id: str
    worker_id: str
    facilitator_id: str
    granted_at: datetime
    expires_at: datetime
    schema_version: str = CONSENT_EVENT_SCHEMA_VERSION
    event_type: str = field(default=EVENT_TYPE_CONSENT_GRANTED)

    def as_audit_detail(self) -> dict[str, str]:
        """Flat strings only: ids and instants, nothing personal."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "context_id": self.context_id,
            "parchi_id": self.parchi_id,
            "worker_id": self.worker_id,
            "facilitator_id": self.facilitator_id,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ConsentRevoked:
    """One worker withdrew consent that had previously been granted.

    The revocation is recorded as a fact; the historical fact that consent was granted is
    preserved in the ConsentGranted event and in the consent record itself.
    """

    event_id: str
    context_id: str
    parchi_id: str
    worker_id: str
    facilitator_id: str
    revoked_at: datetime
    schema_version: str = CONSENT_EVENT_SCHEMA_VERSION
    event_type: str = field(default=EVENT_TYPE_CONSENT_REVOKED)

    def as_audit_detail(self) -> dict[str, str]:
        """Flat strings only: ids and instants, nothing personal."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "context_id": self.context_id,
            "parchi_id": self.parchi_id,
            "worker_id": self.worker_id,
            "facilitator_id": self.facilitator_id,
            "revoked_at": self.revoked_at.isoformat(),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class AssistClaim:
    """One facilitator assisted with one claim under one consent context.

    Records that assistance was provided. The parchi_id is a reference -- the event does NOT
    contain the parchi's contents, the worker's personal details, or any credential.
    """

    event_id: str
    context_id: str
    parchi_id: str
    worker_id: str
    facilitator_id: str
    assisted_at: datetime
    schema_version: str = CONSENT_EVENT_SCHEMA_VERSION
    event_type: str = field(default=EVENT_TYPE_ASSIST_CLAIM)

    def as_audit_detail(self) -> dict[str, str]:
        """Flat strings only: ids and instants, nothing personal."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "context_id": self.context_id,
            "parchi_id": self.parchi_id,
            "worker_id": self.worker_id,
            "facilitator_id": self.facilitator_id,
            "assisted_at": self.assisted_at.isoformat(),
            "schema_version": self.schema_version,
        }
