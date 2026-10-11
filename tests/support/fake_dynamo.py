"""A tiny in-process DynamoDB double for the consent adapter.

It is NOT a DynamoDB emulator. It implements exactly the four operations the consent adapter
performs, and it exists to prove the adapter's contract offline -- in particular that a
conditional put with a stale version really does fail, which is the one behaviour the digest of
this milestone turns on. Its `query` ignores the index name and matches on the attribute, which
is enough for a single-attribute GSI lookup.

A failure here is a failure of the adapter's *logic*. It says nothing about DynamoDB's own
conditional-write semantics, which only a real or LocalStack-backed test can exercise; that
limitation is reported rather than papered over.
"""

from __future__ import annotations

from typing import Any


class ConditionalCheckFailed(Exception):
    """Raised with the shape botocore uses, so `conditional_write()` translates it."""

    def __init__(self, message: str = "ConditionalCheckFailedException") -> None:
        super().__init__(message)
        self.code = "ConditionalCheckFailedException"
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}


def _eval_condition(
    expression: str,
    item: dict[str, Any] | None,
    names: dict[str, str],
    values: dict[str, Any],
) -> bool:
    """Evaluate the subset of condition expressions the adapter writes.

    Supports `attribute_not_exists(name)`, `name = :value`, and their ` OR ` combination.
    """
    for clause in expression.replace(" ", "").split("OR"):
        if clause.startswith("attribute_not_exists(") and clause.endswith(")"):
            name = clause[len("attribute_not_exists(") : -1]
            name = names.get(name, name)
            if item is None or name not in item:
                return True
        elif "=" in clause:
            name, token = clause.split("=", 1)
            name = names.get(name, name)
            if item is not None and item.get(name) == values.get(token):
                return True
    return False


class FakeDynamoTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def put_item(
        self,
        *,
        Item: dict[str, Any],
        ConditionExpression: str | None = None,
        ExpressionAttributeNames: dict[str, str] | None = None,
        ExpressionAttributeValues: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # The consent table is keyed by `scope_key`; that is the only hash key this double
        # needs to understand.
        key = Item.get("scope_key")
        existing = self.items.get(key)
        if ConditionExpression is not None and not _eval_condition(
            ConditionExpression,
            existing,
            ExpressionAttributeNames or {},
            ExpressionAttributeValues or {},
        ):
            raise ConditionalCheckFailed()
        self.items[key] = dict(Item)
        return {}

    def get_item(self, *, Key: dict[str, Any], ConsistentRead: bool = False) -> dict[str, Any]:
        item = self.items.get(Key.get("scope_key"))
        return {"Item": dict(item)} if item is not None else {}

    def query(
        self,
        *,
        IndexName: str | None = None,
        KeyConditionExpression: str | None = None,
        ExpressionAttributeValues: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        values = ExpressionAttributeValues or {}
        attribute, token = (part.strip() for part in str(KeyConditionExpression).split("=", 1))
        wanted = values.get(token)
        return {"Items": [dict(i) for i in self.items.values() if i.get(attribute) == wanted]}


class FakeDynamoResource:
    """What `dynamo_resource().Table(name)` returns, with one table per name."""

    def __init__(self) -> None:
        self._tables: dict[str, FakeDynamoTable] = {}

    def Table(self, name: str) -> FakeDynamoTable:
        """boto3's method name, cased to match the resource API the adapter calls."""
        return self._tables.setdefault(name, FakeDynamoTable())
