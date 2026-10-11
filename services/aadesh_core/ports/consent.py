"""Consent persistence port.

Consent has to outlive the request that created it. A worker grants it in one Lambda
invocation; the authorization check that depends on it happens in a later, unrelated one, so a
consent held in a process's memory is the same as no consent at all. This port is the contract
the durable adapter implements, and the contract the in-memory adapter is held to.

It is deliberately scope-keyed. One (worker, facilitator, parchi) has at most ONE consent
record at a time, because the only question assistance asks is "is there a live consent for
this scope?". A store that could hold two live records for one scope could answer that question
two ways, and revoking the record the worker holds would leave the other quietly authorizing --
which is the failure this shape exists to make unrepresentable. A later grant supersedes the
record; a revocation marks it.

Both writes move the record's `version`, and every write is a compare-and-set against the
version the caller read. That is what stops a grant formed before a revocation from restoring
the consent afterwards: its write carries a stale version and is refused, rather than being
applied to a state nobody observed.

The port stores only what the domain already carries -- ids and instants -- plus the actor who
granted or revoked it. No name, contact detail or identity document crosses this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from aadesh_core.consent import ClaimAssistanceContext


@dataclass(frozen=True, slots=True)
class StoredConsent:
    """A consent record together with the concurrency metadata the store owns.

    `version` is not part of the domain's consent model, and it is not supposed to be: it is a
    storage-level sequencer that lets a caller say "apply this only if the record is still the
    one I read". `granted_by`/`revoked_by` are the authenticated actors, kept as provenance
    rather than folded into the consent object.
    """

    consent: ClaimAssistanceContext
    version: int
    granted_by: str | None = None
    revoked_by: str | None = None


@runtime_checkable
class ConsentStore(Protocol):
    def find_live(
        self,
        *,
        worker_id: str,
        facilitator_id: str,
        parchi_id: str,
        now: datetime,
    ) -> ClaimAssistanceContext | None:
        """The consent that currently authorizes this exact scope, or None.

        Returns a record only when it names the same worker, facilitator and parchi, was
        granted, has not been revoked, and has not expired at `now`. A missing, malformed,
        mismatched, revoked or expired record is None -- the caller denies on None and never
        treats the absence as permission.

        MUST NOT treat a DynamoDB TTL deletion as the expiry check. TTL reclaims storage
        asynchronously and may lag by hours; expiry is decided from `expires_at` on every call.
        """
        ...

    def get(self, context_id: str) -> StoredConsent | None:
        """The record a worker holds the handle for, or None. Used by revocation."""
        ...

    def load(
        self,
        *,
        worker_id: str,
        facilitator_id: str,
        parchi_id: str,
    ) -> StoredConsent | None:
        """The current record for a scope, or None. Used to read the version a write must match."""
        ...

    def save(
        self,
        consent: ClaimAssistanceContext,
        *,
        expected_version: int,
        actor_id: str,
    ) -> StoredConsent:
        """Persist a consent, but only if the scope is still at `expected_version`.

        `expected_version` is 0 for a scope with no record yet. A mismatch means someone else
        changed the record first, and MUST raise `ConsentStoreConflict` without writing:
        applying the write anyway would let a stale grant (or a second revocation) overwrite a
        newer decision, which is exactly the race this parameter exists to lose.
        """
        ...
