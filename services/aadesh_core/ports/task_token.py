"""Where a Step Functions task token waits for its worker.

The ASL holds each parchi in PENDING_ACK with `lambda:invoke.waitForTaskToken`. That call
returns immediately; the machine resumes only when someone calls SendTaskSuccess with the
token. The token therefore has to survive between two different Lambda invocations, possibly
on two different containers, possibly hours apart.

Deliberately narrow: a token is stored against a parchi id and read back once. There is no
enumeration and no listing, for the same reason `AcknowledgementTokenStore` has none -- a
capability to list every suspended execution is a capability nobody needs.

**What `expires_at` is and is not.** It is a hint to the storage layer, not a rule this port
enforces: neither signature takes a `now`, so neither implementation can decide that a token
has expired. The in-memory adapter keeps a token until it is popped; the DynamoDB adapter
sets a TTL that reclaims the item some time after `expires_at`. Those differ, and the contract
suite deliberately does not test expiry for that reason. Expiry of the *machine* is enforced
by Step Functions, which rejects a task token past its timeout -- that is the guarantee that
matters, and it does not depend on this store. `expires_at` exists so the store does not
retain a token indefinitely.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class TaskTokenStore(Protocol):
    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None:
        """Record the token for `parchi_id`. MUST refuse a naive `expires_at`."""
        ...

    def pop(self, *, parchi_id: str) -> str | None:
        """Read the token AND remove it, as one operation.

        Removing on read is the property that makes a retried resume safe: the second attempt
        finds nothing and does not call SendTaskSuccess twice. Returns None when there is no
        token, which is an ordinary condition -- the machine may already have timed out.
        """
        ...

    def peek(self, *, parchi_id: str) -> str | None:
        """Read without removing, for diagnostics. MUST NOT be used to resume a machine."""
        ...
