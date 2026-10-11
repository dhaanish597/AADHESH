"""In-memory consent store.

The reference implementation of `ConsentStore`, and the adapter the local demonstration and the
tests use. It is held to the same contract as the DynamoDB adapter, including the compare-and-set
that makes a stale write lose to a newer revocation.

The lock is here because that guarantee is not a property of a single dict assignment: reading
the version, checking it, and replacing the record has to be indivisible, or two threads revoke
and grant "at the same time" and the outcome is whichever one the scheduler happened to run last.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from aadesh_core.consent import ClaimAssistanceContext
from aadesh_core.errors import ConsentStoreConflict
from aadesh_core.ports.consent import StoredConsent


def _scope_key(*, worker_id: str, facilitator_id: str, parchi_id: str) -> str:
    return f"consent#{worker_id}#{facilitator_id}#{parchi_id}"


def _live(
    consent: ClaimAssistanceContext,
    *,
    worker_id: str,
    facilitator_id: str,
    parchi_id: str,
    now: datetime,
) -> bool:
    return (
        consent.worker_id == worker_id
        and consent.facilitator_id == facilitator_id
        and consent.parchi_id == parchi_id
        and consent.consent_granted
        and consent.revoked_at is None
        and consent.granted_at <= now < consent.expires_at
    )


@dataclass
class _Record:
    consent: ClaimAssistanceContext
    version: int
    granted_by: str | None = None
    revoked_by: str | None = None


class InMemoryConsentStore:
    """Scope-keyed, versioned consent storage. Survives for the life of the process only.

    This is a local/test adapter. It is NOT a cache in front of a durable store, and nothing
    wires it on AWS: there the DynamoDB adapter is the one and only source of consent, so there
    is no in-memory copy that could keep a revoked consent looking live.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, _Record] = {}
        self._context_to_scope: dict[str, str] = {}

    # -- reads --------------------------------------------------------------

    def find_live(
        self,
        *,
        worker_id: str,
        facilitator_id: str,
        parchi_id: str,
        now: datetime,
    ) -> ClaimAssistanceContext | None:
        scope = _scope_key(worker_id=worker_id, facilitator_id=facilitator_id, parchi_id=parchi_id)
        with self._lock:
            record = self._records.get(scope)
            if record is None:
                return None
            consent = record.consent
        # Validated OUTSIDE the lock, and after it: a malformed record is a refusal, not a
        # crash, and a slow failure must not hold the store open.
        try:
            if not _live(
                consent,
                worker_id=worker_id,
                facilitator_id=facilitator_id,
                parchi_id=parchi_id,
                now=now,
            ):
                return None
        except Exception:
            return None
        return consent

    def get(self, context_id: str) -> StoredConsent | None:
        with self._lock:
            scope = self._context_to_scope.get(context_id)
            record = self._records.get(scope) if scope is not None else None
            if record is None or record.consent.context_id != context_id:
                return None
            return StoredConsent(
                consent=record.consent,
                version=record.version,
                granted_by=record.granted_by,
                revoked_by=record.revoked_by,
            )

    def load(self, *, worker_id: str, facilitator_id: str, parchi_id: str) -> StoredConsent | None:
        scope = _scope_key(worker_id=worker_id, facilitator_id=facilitator_id, parchi_id=parchi_id)
        with self._lock:
            record = self._records.get(scope)
            if record is None:
                return None
            return StoredConsent(
                consent=record.consent,
                version=record.version,
                granted_by=record.granted_by,
                revoked_by=record.revoked_by,
            )

    # -- writes -------------------------------------------------------------

    def save(
        self,
        consent: ClaimAssistanceContext,
        *,
        expected_version: int,
        actor_id: str,
    ) -> StoredConsent:
        scope = _scope_key(
            worker_id=consent.worker_id,
            facilitator_id=consent.facilitator_id,
            parchi_id=consent.parchi_id,
        )
        with self._lock:
            record = self._records.get(scope)
            current_version = record.version if record is not None else 0
            if current_version != expected_version:
                raise ConsentStoreConflict()
            new_version = expected_version + 1
            granted_by = record.granted_by if record is not None else None
            revoked_by = record.revoked_by if record is not None else None
            if consent.revoked_at is None:
                granted_by = actor_id
                revoked_by = None
            else:
                revoked_by = actor_id
            self._records[scope] = _Record(
                consent=consent,
                version=new_version,
                granted_by=granted_by,
                revoked_by=revoked_by,
            )
            if record is not None:
                self._context_to_scope.pop(record.consent.context_id, None)
            self._context_to_scope[consent.context_id] = scope
            return StoredConsent(
                consent=consent,
                version=new_version,
                granted_by=granted_by,
                revoked_by=revoked_by,
            )
