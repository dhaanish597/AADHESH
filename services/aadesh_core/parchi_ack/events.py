"""The acknowledgement audit event.

`ParchiAcknowledged` is the record that makes this sentence provable:

    "Worker X acknowledged Parchi Y at time T."

...and it is deliberately thin, because it is also the record that gets shipped to a log sink
and kept forever. The test it has to pass is the same one the QR passes: everything in here
must be safe to leave lying around.

So there is no `token` field. There IS a `token_reference`, which is `tok_` plus the first 16
hex characters of the token's SHA-256 -- enough to correlate "which link was used" across
audit lines, useless for replaying it. `tests/unit/test_parchi_privacy.py` walks the event's
serialised form looking for the raw token, and fails if it is anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aadesh_core.domain import AcknowledgementMethod

PARCHI_EVENT_SCHEMA_VERSION = "parchi-event/1"
"""Stamped on every event so a consumer can tell which shape of record it is reading."""

EVENT_TYPE_PARCHI_ACKNOWLEDGED = "ParchiAcknowledged"
EVENT_TYPE_PARCHI_SEALED = "ParchiSealed"


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
