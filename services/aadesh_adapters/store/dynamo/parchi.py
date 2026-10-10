"""DynamoDB parchi store. The durable home of the worker's evidence record.

Two properties of the in-memory reference are load-bearing and are preserved here by
conditional writes rather than by a lock:

  * a SEALED parchi cannot be overwritten -- the write is refused by a condition on the
    stored `state` attribute, so the check and the write are one operation;
  * `save_new` is atomic with respect to an idempotency key -- a marker item is created
    conditionally first, so two callers holding the same key cannot both win.

The record itself is stored as a JSON string under `record`, and the fields the access
patterns need (`site_id`, `worker_id`, `state`) are denormalised onto the item for the GSIs.
Storing JSON rather than a nested DynamoDB map is deliberate: the serde round-trip is then
byte-for-byte and it cannot be perturbed by DynamoDB's type coercions (a `None`, an empty
list, a numeric string). The JSON is the evidence; the denormalised attributes are an index
over it.
"""

from __future__ import annotations

import json
from typing import Any

from aadesh_adapters.store.dynamo.client import (
    ConditionalCheckFailed,
    conditional_write,
    dynamo_resource,
    table_name,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads
from aadesh_core.domain import ParchiState
from aadesh_core.errors import DuplicateIdempotencyKey, IllegalParchiTransition
from aadesh_core.parchi import Parchi

MARKER_PREFIX = "idem#"


def _marker_key(idempotency_key: str) -> str:
    return f"{MARKER_PREFIX}{idempotency_key}"


class DynamoParchiStore:
    """`ParchiAckStore` over DynamoDB."""

    def __init__(self, *, table_name_override: str | None = None, dynamo: Any = None) -> None:
        self._table_name = table_name_override or table_name("parchis")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _item(parchi: Parchi) -> dict[str, Any]:
        item: dict[str, Any] = {
            "parchi_id": parchi.parchi_id,
            "kind": "parchi",
            "site_id": parchi.site_id,
            "worker_id": parchi.worker_id,
            "state": parchi.state.value,
            "record": json.dumps(dumps(parchi), sort_keys=True, ensure_ascii=False),
        }
        if parchi.idempotency_key is not None:
            item["idempotency_key"] = parchi.idempotency_key
        return item

    @staticmethod
    def _parchi(item: dict[str, Any]) -> Parchi:
        return loads(json.loads(item["record"]), Parchi)

    # -- the port -----------------------------------------------------------

    def save(self, parchi: Parchi) -> None:
        try:
            with conditional_write():
                self.table.put_item(
                    Item=self._item(parchi),
                    ConditionExpression=("attribute_not_exists(parchi_id) OR #state <> :sealed"),
                    ExpressionAttributeNames={"#state": "state"},
                    ExpressionAttributeValues={":sealed": ParchiState.SEALED.value},
                )
        except ConditionalCheckFailed as exc:
            raise IllegalParchiTransition(
                f"Parchi {parchi.parchi_id} is sealed and cannot be overwritten. "
                f"Sealed records are append-only evidence."
            ) from exc

    def save_new(self, parchi: Parchi) -> None:
        key = parchi.idempotency_key
        if key is not None:
            marker = {
                "parchi_id": _marker_key(key),
                "kind": "idempotency-marker",
                "target": parchi.parchi_id,
            }
            try:
                with conditional_write():
                    self.table.put_item(
                        Item=marker,
                        ConditionExpression="attribute_not_exists(parchi_id)",
                    )
            except ConditionalCheckFailed as exc:
                existing = self.table.get_item(
                    Key={"parchi_id": _marker_key(key)}, ConsistentRead=True
                ).get("Item")
                target = (existing or {}).get("target")
                if target and self.get(str(target)) is not None:
                    raise DuplicateIdempotencyKey(key) from exc
                # A marker with no surviving parchi is the debris of a crashed write, not a
                # competing record. Claim it and continue: refusing here would strand that
                # worker's parchi forever.
                self.table.put_item(Item=marker)

        try:
            with conditional_write():
                self.table.put_item(
                    Item=self._item(parchi),
                    ConditionExpression="attribute_not_exists(parchi_id)",
                )
        except ConditionalCheckFailed as exc:
            raise DuplicateIdempotencyKey(key or parchi.parchi_id) from exc

    def get(self, parchi_id: str) -> Parchi | None:
        item = self.table.get_item(Key={"parchi_id": parchi_id}, ConsistentRead=True).get("Item")
        return self._parchi(item) if item and item.get("record") else None

    def for_site(self, site_id: str) -> tuple[Parchi, ...]:
        return self._query_index("site_id-index", "site_id", site_id)

    def for_worker(self, worker_id: str) -> tuple[Parchi, ...]:
        return self._query_index("worker_id-index", "worker_id", worker_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> Parchi | None:
        marker = self.table.get_item(
            Key={"parchi_id": _marker_key(idempotency_key)}, ConsistentRead=True
        ).get("Item")
        target = (marker or {}).get("target")
        if not target:
            return None
        return self.get(str(target))

    def _query_index(self, index: str, attribute: str, value: str) -> tuple[Parchi, ...]:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            IndexName=index,
            KeyConditionExpression=Key(attribute).eq(value),
        )
        return tuple(self._parchi(item) for item in response.get("Items", []) if item.get("record"))
