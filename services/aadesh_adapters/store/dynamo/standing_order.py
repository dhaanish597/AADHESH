"""DynamoDB persistence for Standing Orders and their trigger runs.

`TriggerRunStore.claim` is the chokepoint that makes duplicate parchis unrepresentable: it is
create-if-absent, and it returns the EXISTING run on a collision rather than raising. Raising
would push the redelivery decision back onto the caller, and the caller is a Step Functions
retry that has no way to make it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from aadesh_adapters.store.dynamo.client import (
    ConditionalCheckFailed,
    conditional_write,
    dynamo_resource,
    table_name,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads
from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import StandingOrder, TriggerRun


class DynamoStandingOrderStore:
    def __init__(self, *, dynamo: Any = None, table_name_override: str | None = None) -> None:
        self._table_name = table_name_override or table_name("standing_orders")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table

    def get(self, standing_order_id: str) -> StandingOrder | None:
        item = self.table.get_item(
            Key={"standing_order_id": standing_order_id}, ConsistentRead=True
        ).get("Item")
        if not item or not item.get("record"):
            return None
        return loads(json.loads(item["record"]), StandingOrder)

    def save(self, order: StandingOrder) -> None:
        """Persist an order. A DRAFT -> CONFIRMED transition replaces the same id on purpose."""
        self.table.put_item(
            Item={
                "standing_order_id": order.standing_order_id,
                "site_id": order.site_id,
                "supervisor_id": order.supervisor_id,
                "status": order.status.value,
                "record": json.dumps(dumps(order), sort_keys=True, ensure_ascii=False),
            }
        )

    def for_site(self, site_id: str) -> Sequence[StandingOrder]:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            IndexName="site_id-index",
            KeyConditionExpression=Key("site_id").eq(site_id),
        )
        return tuple(
            loads(json.loads(item["record"]), StandingOrder)
            for item in response.get("Items", [])
            if item.get("record")
        )


class DynamoTriggerRunStore:
    def __init__(self, *, dynamo: Any = None, table_name_override: str | None = None) -> None:
        self._table_name = table_name_override or table_name("trigger_runs")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table

    def claim(self, run: TriggerRun) -> TriggerRun:
        try:
            with conditional_write():
                self.table.put_item(
                    Item={
                        "fingerprint": run.fingerprint,
                        "site_id": run.site_id,
                        "standing_order_id": run.standing_order_id,
                        "status": run.status.value,
                        "record": json.dumps(dumps(run), sort_keys=True, ensure_ascii=False),
                    },
                    ConditionExpression="attribute_not_exists(fingerprint)",
                )
            return run
        except ConditionalCheckFailed:
            existing = self.get(run.fingerprint)
            if existing is None:  # pragma: no cover -- a lost race must leave a run behind
                raise
            return existing

    def get(self, fingerprint: str) -> TriggerRun | None:
        item = self.table.get_item(Key={"fingerprint": fingerprint}, ConsistentRead=True).get(
            "Item"
        )
        if not item or not item.get("record"):
            return None
        return loads(json.loads(item["record"]), TriggerRun)

    def complete(self, fingerprint: str, *, completed_at: datetime | None = None) -> None:
        existing = self.get(fingerprint)
        if existing is None:
            raise KeyError(f"No trigger run for fingerprint {fingerprint!r}.")
        if existing.completed_at is not None:
            return
        from dataclasses import replace as _replace

        completed = _replace(
            existing,
            status=StandingOrderStatus.COMPLETED,
            completed_at=completed_at or existing.started_at,
        )
        self.table.update_item(
            Key={"fingerprint": fingerprint},
            UpdateExpression="SET #status = :status, #record = :record",
            ExpressionAttributeNames={"#status": "status", "#record": "record"},
            ExpressionAttributeValues={
                ":status": completed.status.value,
                ":record": json.dumps(dumps(completed), sort_keys=True, ensure_ascii=False),
            },
        )
