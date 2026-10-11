"""DynamoDB persistence for worker consent.

This is the adapter that makes consent survive independent Lambda invocations. Everything about
its shape follows from one requirement: an authorization decision must never be made against a
consent the store has since revoked.

Key structure
-------------
Table `aadesh-consents`, hash key `scope_key = consent#<worker>#<facilitator>#<parchi>`.

  * The scope IS the key. One (worker, facilitator, parchi) therefore has at most one consent
    record, so "is there a live consent for this scope?" has exactly one answer and revoking the
    record a worker holds cannot leave a second live one behind.
  * A `context_id-index` GSI answers the other question -- "the record this handle names" -- so a
    worker can revoke by the context id they were given without knowing the scope key.
  * `version` is a monotonically increasing counter written on every change. Every write is a
    conditional write against it, which is what makes a grant formed before a revocation lose
    that race instead of overwriting it.
  * `ttl` deletes the item eventually. It is NOT the authorization check: `find_live` compares
    `expires_at` against `now` on every call, because TTL deletion lags by up to 48 hours and an
    authorization boundary cannot wait for housekeeping.

Access patterns
---------------
  * grant    : read scope (load) -> conditional put with the version read
  * revoke   : query GSI by context id -> conditional put with the version read
  * assist   : get scope (find_live), validate scope + expiry + revocation, then Cedar

Everything stored is an id, an instant, a boolean or the serialised domain record. No name,
contact detail or identity document is written here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from aadesh_adapters.store.dynamo.client import (
    conditional_write,
    dynamo_resource,
    table_name,
)
from aadesh_adapters.store.dynamo.serde import SerdeError, dumps, loads
from aadesh_core.consent import ClaimAssistanceContext
from aadesh_core.errors import ConsentStoreConflict
from aadesh_core.ports.consent import StoredConsent

KIND = "consent"


def _epoch(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError(
            "Refusing to store a naive instant. A TTL computed from a naive datetime expires "
            "in whichever zone the host happens to be in."
        )
    return int(value.timestamp())


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


class DynamoConsentStore:
    """Consent records in DynamoDB, with compare-and-set writes."""

    def __init__(self, *, dynamo: Any = None, table_name_override: str | None = None) -> None:
        self._table_name = table_name_override or table_name("consents")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table

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
        item = self._get_scope(scope)
        if item is None:
            return None
        record = self._decode_for_read(item)
        if record is None:
            return None
        try:
            if not _live(
                record.consent,
                worker_id=worker_id,
                facilitator_id=facilitator_id,
                parchi_id=parchi_id,
                now=now,
            ):
                return None
        except Exception:
            return None
        return record.consent

    def get(self, context_id: str) -> StoredConsent | None:
        response = self.table.query(
            IndexName="context_id-index",
            KeyConditionExpression="context_id = :context_id",
            ExpressionAttributeValues={":context_id": context_id},
        )
        items = response.get("Items", [])
        for item in items:
            record = self._decode_for_read(item)
            if record is not None and record.consent.context_id == context_id:
                return record
        return None

    def load(self, *, worker_id: str, facilitator_id: str, parchi_id: str) -> StoredConsent | None:
        scope = _scope_key(worker_id=worker_id, facilitator_id=facilitator_id, parchi_id=parchi_id)
        item = self._get_scope(scope)
        if item is None:
            return None
        return self._decode_for_read(item)

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
        new_version = expected_version + 1
        item: dict[str, Any] = {
            "scope_key": scope,
            "kind": KIND,
            "context_id": consent.context_id,
            "worker_id": consent.worker_id,
            "facilitator_id": consent.facilitator_id,
            "parchi_id": consent.parchi_id,
            "version": new_version,
            "revoked": consent.revoked_at is not None,
            "expires_at": consent.expires_at.isoformat(),
            "record": json.dumps(dumps(consent), sort_keys=True, ensure_ascii=False),
            "ttl": _epoch(consent.expires_at),
            "written_at": datetime.now(UTC).isoformat(),
        }
        if consent.revoked_at is None:
            item["granted_by"] = actor_id
            item["revoked_by"] = None
        else:
            item["revoked_by"] = actor_id
        try:
            with conditional_write():
                self.table.put_item(
                    Item=item,
                    # The compare-and-set. `expected_version` is 0 for a scope with no record,
                    # so a create and a replace are the same expression.
                    ConditionExpression="attribute_not_exists(#v) OR #v = :expected",
                    ExpressionAttributeNames={"#v": "version"},
                    ExpressionAttributeValues={":expected": expected_version},
                )
        except Exception as exc:
            if type(exc).__name__ == "ConditionalCheckFailed":
                raise ConsentStoreConflict() from exc
            raise
        return StoredConsent(
            consent=consent,
            version=new_version,
            granted_by=item.get("granted_by"),
            revoked_by=item.get("revoked_by"),
        )

    # -- internals ----------------------------------------------------------

    def _get_scope(self, scope: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"scope_key": scope}, ConsistentRead=True).get("Item")
        if not item or not item.get("record"):
            return None
        return item

    @staticmethod
    def _decode_for_read(item: dict[str, Any]) -> StoredConsent | None:
        """Reconstruct a stored record, or None if it cannot be trusted.

        A record whose fields do not match the domain model, or that cannot be reconstructed
        without loss, is not a slightly-wrong consent -- it is not consent at all. Returning
        None makes the caller deny, which is the only safe reading of a malformed record.
        """
        try:
            consent = loads(json.loads(item["record"]), ClaimAssistanceContext)
            version = int(item["version"])
        except (SerdeError, ValueError, KeyError, TypeError):
            return None
        return StoredConsent(
            consent=consent,
            version=version,
            granted_by=item.get("granted_by"),
            revoked_by=item.get("revoked_by"),
        )
