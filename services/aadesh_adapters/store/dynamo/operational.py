"""Operational state in DynamoDB: acknowledgement tokens, the idempotency ledger, the Step
Functions task tokens, and the short-lived QR link cache.

Why one table rather than four. These records share three properties that decide how they are
stored and reaped, and differ in no other way that matters: they are keyed by an opaque id
that is never enumerated, they are small, and they all expire on their own TTL. Giving each
its own table would multiply the deployed resources without giving any of them a distinct
access pattern. The `kind` attribute names which record an item is, so a reader cannot mistake
a task token for an acknowledgement token.

The interesting contract here is `execute_once`. It is implemented with a lease: a claim item
is created conditionally, the winner runs the operation, and the winner records the result on
the same item. A loser polls for the result and steals the lease if the winner dies.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, TypeVar

from aadesh_adapters.store.dynamo.client import (
    ConditionalCheckFailed,
    DynamoUnavailable,
    conditional_write,
    dynamo_resource,
    table_name,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads
from aadesh_core.errors import TokenRejected, TokenRejectionReason
from aadesh_core.parchi_ack.service import AcknowledgementOutcome
from aadesh_core.parchi_ack.tokens import AcknowledgementToken, TokenState

T = TypeVar("T")

#: Result kind tag -> the class that can reconstruct it. Registering the type explicitly is
#: what lets the ledger stay generic while still refusing to guess at an unknown payload.
RESULT_CODECS: dict[str, Any] = {AcknowledgementOutcome.__name__: AcknowledgementOutcome}

CLAIM_LEASE_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.1
POLL_DEADLINE_SECONDS = 8.0


def _epoch(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError(
            "Refusing to store a naive instant. A TTL computed from a naive datetime expires "
            "in whichever zone the host happens to be in."
        )
    return int(value.timestamp())


class _OperationalTable:
    def __init__(self, *, dynamo: Any = None, table_name_override: str | None = None) -> None:
        self._table_name = table_name_override or table_name("operational")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table


class DynamoAcknowledgementTokenStore(_OperationalTable):
    """Holds acknowledgement tokens. It cannot enumerate: there is no `all()`, `for_worker()`
    or `for_parchi()`. That is the security property, not an oversight."""

    def put(self, token: AcknowledgementToken) -> None:
        self.table.put_item(
            Item={
                "pk": f"token#{token.token_hash}",
                "kind": "ack-token",
                "record": json.dumps(dumps(token), sort_keys=True, ensure_ascii=False),
                "ttl": _epoch(token.expires_at),
            }
        )

    def get(self, token_hash: str) -> AcknowledgementToken | None:
        item = self.table.get_item(Key={"pk": f"token#{token_hash}"}, ConsistentRead=True).get(
            "Item"
        )
        if not item or not item.get("record"):
            return None
        return loads(json.loads(item["record"]), AcknowledgementToken)

    def consume(self, token_hash: str, *, at: datetime, event_id: str) -> AcknowledgementToken:
        """Compare-and-set. The loser loses here, not at the database layer above."""
        item = self.table.get_item(Key={"pk": f"token#{token_hash}"}, ConsistentRead=True).get(
            "Item"
        )
        if not item or not item.get("record"):
            raise TokenRejected(TokenRejectionReason.UNKNOWN)

        token = loads(json.loads(item["record"]), AcknowledgementToken)
        if token.state == TokenState.CONSUMED:
            raise TokenRejected(TokenRejectionReason.CONSUMED)
        if token.is_expired(at):
            raise TokenRejected(TokenRejectionReason.EXPIRED)

        consumed = replace(
            token, state=TokenState.CONSUMED, consumed_at=at, consumed_event_id=event_id
        )
        try:
            with conditional_write():
                self.table.put_item(
                    Item={
                        "pk": f"token#{token_hash}",
                        "kind": "ack-token",
                        "record": json.dumps(dumps(consumed), sort_keys=True, ensure_ascii=False),
                        "ttl": _epoch(token.expires_at),
                    },
                    ConditionExpression="attribute_not_exists(#state) OR #state <> :consumed",
                    ExpressionAttributeNames={"#state": "state"},
                    ExpressionAttributeValues={":consumed": TokenState.CONSUMED.value},
                )
        except ConditionalCheckFailed as exc:
            # Somebody used the link first. Nothing was written by this call.
            raise TokenRejected(TokenRejectionReason.CONSUMED) from exc
        return consumed


class DynamoIdempotencyLedger(_OperationalTable):
    """Runs an operation at most once per key. Every later caller gets the first result.

    A lease, not a lock service: a claim item is created conditionally, the winner writes the
    result onto it, and a loser polls for the result. If the winner dies mid-operation the
    lease goes stale and the next caller steals it -- otherwise that one key would be stuck
    forever, silently, for the one worker unlucky enough to hit the crash.
    """

    def execute_once(self, *, key: str, compute: Callable[[], T]) -> T:
        if not key.strip():
            raise ValueError("execute_once requires a non-empty key")

        pk = f"ledger#{key}"
        owner = secrets.token_hex(8)

        if self._claim(pk, owner):
            return self._run(pk, owner, compute)

        deadline = time.monotonic() + POLL_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            item = self.table.get_item(Key={"pk": pk}, ConsistentRead=True).get("Item")
            if item is None:
                if self._claim(pk, owner):
                    return self._run(pk, owner, compute)
            elif item.get("state") == "done":
                return self._replay(item)
            elif self._is_stale(item) and self._steal(pk, str(item.get("owner", "")), owner):
                return self._run(pk, owner, compute)
            time.sleep(POLL_INTERVAL_SECONDS)

        raise DynamoUnavailable(
            f"Idempotency key {key!r} is held by another in-flight operation that has not "
            f"finished or gone stale within {POLL_DEADLINE_SECONDS:.0f}s."
        )

    # -- internals ---------------------------------------------------------

    def _claim(self, pk: str, owner: str) -> bool:
        try:
            with conditional_write():
                self.table.put_item(
                    Item={
                        "pk": pk,
                        "kind": "ledger",
                        "state": "claimed",
                        "owner": owner,
                        "claimed_at": _epoch(datetime.now(UTC)),
                    },
                    ConditionExpression="attribute_not_exists(pk)",
                )
            return True
        except ConditionalCheckFailed:
            return False

    def _run(self, pk: str, owner: str, compute: Callable[[], T]) -> T:
        try:
            result = compute()
        except BaseException:
            # A failed compute must leave the key unclaimed, or a genuine retry could never
            # run. Deleting our own claim (and only our own) is the recovery path.
            self._release(pk, owner)
            raise
        kind = type(result).__name__
        if kind not in RESULT_CODECS:
            self._release(pk, owner)
            raise DynamoUnavailable(
                f"IdempotencyLedger cannot persist a result of type {kind!r}. Register a codec "
                f"in RESULT_CODECS, or the replay of this key could not be answered."
            )
        with conditional_write():
            self.table.update_item(
                Key={"pk": pk},
                UpdateExpression="SET #state = :done, #result = :result, result_kind = :kind",
                ConditionExpression="#owner = :owner",
                ExpressionAttributeNames={
                    "#state": "state",
                    "#result": "result",
                    "#owner": "owner",
                },
                ExpressionAttributeValues={
                    ":done": "done",
                    ":result": json.dumps(dumps(result), sort_keys=True, ensure_ascii=False),
                    ":kind": kind,
                    ":owner": owner,
                },
            )
        return result

    def _replay(self, item: dict[str, Any]) -> Any:
        kind = item.get("result_kind")
        codec = RESULT_CODECS.get(str(kind))
        if codec is None:
            raise DynamoUnavailable(
                f"Idempotency ledger holds a result of unknown kind {kind!r}; it cannot be "
                f"reconstructed, and guessing would hand back a different fact."
            )
        return loads(json.loads(item["result"]), codec)

    @staticmethod
    def _is_stale(item: dict[str, Any]) -> bool:
        claimed_at = item.get("claimed_at")
        if claimed_at is None:
            return True
        return (time.time() - float(claimed_at)) > CLAIM_LEASE_SECONDS

    def _steal(self, pk: str, previous_owner: str, owner: str) -> bool:
        try:
            with conditional_write():
                self.table.update_item(
                    Key={"pk": pk},
                    UpdateExpression="SET #owner = :new, claimed_at = :now",
                    ConditionExpression="#owner = :old AND #state = :claimed",
                    ExpressionAttributeNames={"#owner": "owner", "#state": "state"},
                    ExpressionAttributeValues={
                        ":new": owner,
                        ":old": previous_owner,
                        ":now": _epoch(datetime.now(UTC)),
                        ":claimed": "claimed",
                    },
                )
            return True
        except ConditionalCheckFailed:
            return False

    def _release(self, pk: str, owner: str) -> None:
        try:
            self.table.delete_item(
                Key={"pk": pk},
                ConditionExpression="#owner = :owner",
                ExpressionAttributeNames={"#owner": "owner"},
                ExpressionAttributeValues={":owner": owner},
            )
        except Exception:
            return


class DynamoTaskTokenStore(_OperationalTable):
    """Holds the Step Functions task token a waiting execution is parked on.

    Delete-on-read is the primitive: `delete_item` with `ReturnValues="ALL_OLD"` removes and
    returns the token in one operation, so a retried resume finds nothing and does not call
    SendTaskSuccess twice.
    """

    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None:
        self.table.put_item(
            Item={
                "pk": f"tasktoken#{parchi_id}",
                "kind": "task-token",
                "task_token": task_token,
                "ttl": _epoch(expires_at),
            }
        )

    def pop(self, *, parchi_id: str) -> str | None:
        response = self.table.delete_item(
            Key={"pk": f"tasktoken#{parchi_id}"}, ReturnValues="ALL_OLD"
        )
        old = response.get("Attributes")
        return old.get("task_token") if old else None

    def peek(self, *, parchi_id: str) -> str | None:
        item = self.table.get_item(Key={"pk": f"tasktoken#{parchi_id}"}, ConsistentRead=True).get(
            "Item"
        )
        return item.get("task_token") if item else None


class DynamoQrLinkCache(_OperationalTable):
    """A short-lived cache of an already-minted acknowledgement link.

    Why this exists, stated plainly: the core stores only the SHA-256 of a token, so a link is
    returned exactly once and cannot be recovered afterwards. The supervisor console shows a
    worker their QR on demand, which means it must be able to re-render a link that was minted
    minutes earlier. This cache is that: the raw payload, keyed by parchi, expiring with the
    token's own TTL and reclaimed by DynamoDB.

    What it is NOT: it is never written to an audit record, it holds no worker detail beyond
    the parchi key, and it can hold nothing at all once the token has expired. The evidence
    records still contain only hashes.
    """

    def put(self, *, parchi_id: str, payload: str, expires_at: datetime) -> None:
        self.table.put_item(
            Item={
                "pk": f"qrlink#{parchi_id}",
                "kind": "qr-link",
                "payload": payload,
                "ttl": _epoch(expires_at),
            }
        )

    def get(self, *, parchi_id: str) -> str | None:
        item = self.table.get_item(Key={"pk": f"qrlink#{parchi_id}"}).get("Item")
        return item.get("payload") if item else None

    def delete(self, *, parchi_id: str) -> None:
        self.table.delete_item(Key={"pk": f"qrlink#{parchi_id}"})
