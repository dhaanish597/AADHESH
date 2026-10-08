"""In-memory adapters for the acknowledgement workflow.

These are the reference implementations of two ports whose contracts are, unusually, about
*concurrency* rather than about storage:

  * `InMemoryAcknowledgementTokenStore.consume` is a compare-and-set. It re-checks the token's
    state inside the lock and refuses a second consumption, so two confirmations racing on the
    same link produce exactly one winner.
  * `InMemoryIdempotencyLedger.execute_once` runs the operation while holding a per-key lock,
    so two racing callers produce one execution and both get the same result object.

Neither is a distributed lock, and neither is pretending to be. This is the in-process
adapter used by tests and local development; a production adapter must provide the same
guarantee from its own storage engine (a conditional write, a unique constraint, a lock
service). The port docstrings state that obligation so the DynamoDB adapter cannot quietly
inherit the weaker "read, then write" version.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import TypeVar

from aadesh_core.errors import TokenRejected, TokenRejectionReason
from aadesh_core.parchi_ack.tokens import AcknowledgementToken, TokenState

T = TypeVar("T")


class InMemoryAcknowledgementTokenStore:
    """Holds acknowledgement tokens. Keys are hashes, values are hash-only records.

    The store cannot enumerate: there is no `all()`, no `for_worker()`, no `for_parchi()`.
    That is not an oversight. "List every outstanding acknowledgement link" is a capability
    nobody in this system needs, and the safest way to not have it is to not implement it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, AcknowledgementToken] = {}

    def put(self, token: AcknowledgementToken) -> None:
        with self._lock:
            self._tokens[token.token_hash] = token

    def get(self, token_hash: str) -> AcknowledgementToken | None:
        with self._lock:
            return self._tokens.get(token_hash)

    def consume(self, token_hash: str, *, at: datetime, event_id: str) -> AcknowledgementToken:
        """Compare-and-set. Raises `TokenRejected` rather than returning None so no caller can
        forget to handle the failure and proceed as if the token were fine.
        """
        with self._lock:
            token = self._tokens.get(token_hash)

            # UNKNOWN is checked first and looks identical to the others to a caller: same
            # exception type, same sentence. Only `reason` differs, and `reason` is for the
            # audit log, never for the response.
            if token is None:
                raise TokenRejected(TokenRejectionReason.UNKNOWN)
            if token.state is TokenState.CONSUMED:
                raise TokenRejected(TokenRejectionReason.CONSUMED)
            if token.is_expired(at):
                raise TokenRejected(TokenRejectionReason.EXPIRED)

            consumed = replace(
                token,
                state=TokenState.CONSUMED,
                consumed_at=at,
                consumed_event_id=event_id,
            )
            self._tokens[token_hash] = consumed
            return consumed


class InMemoryIdempotencyLedger:
    """Runs an operation once per key; every later caller gets the first caller's result.

    The per-key lock, not a global one, so unrelated keys do not serialise against each other
    -- and so an operation that itself calls `execute_once` under a *different* key cannot
    deadlock.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._results: dict[str, object] = {}

    def execute_once(self, *, key: str, compute: Callable[[], T]) -> T:
        if not key.strip():
            raise ValueError("execute_once requires a non-empty key")

        with self._guard:
            if key in self._results:
                return self._results[key]  # type: ignore[return-value]
            lock = self._locks.setdefault(key, threading.Lock())

        with lock:
            # Re-check under the per-key lock: another thread may have completed between the
            # optimistic read above and acquiring this lock. That re-check is the whole point.
            with self._guard:
                if key in self._results:
                    return self._results[key]  # type: ignore[return-value]

            # Deliberately outside the guard lock but inside the per-key lock. If `compute`
            # raises, nothing is recorded, so the key stays unclaimed and a genuine retry runs.
            result = compute()

            with self._guard:
                self._results[key] = result
            return result
