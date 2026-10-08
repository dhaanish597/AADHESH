"""Ports for the parchi acknowledgement workflow.

Two of these are deliberately narrow, and the narrowness is the security property:

  * `AcknowledgementTokenStore` can store and consume a token. It cannot enumerate tokens and
    it cannot read a token by anything other than its hash, so "list every outstanding
    acknowledgement link" is not an operation this system can perform.
  * `IdempotencyLedger.execute_once` is the single-writer point where a repeated request
    stops being a second request. See `execute_once` for why this is not a try/except.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

from aadesh_core.parchi import Parchi
from aadesh_core.ports.parchi_store import ParchiStore

if TYPE_CHECKING:
    # Annotation-only, and deliberately not a runtime import. `aadesh_core.parchi_ack` imports
    # this module, so importing back into it at runtime would make the port reachable only
    # when something else happened to load the workflow package first -- which is precisely
    # backwards for the module an adapter author imports first. See
    # tests/unit/test_ports_import_order.py.
    from aadesh_core.parchi_ack.tokens import AcknowledgementToken

T = TypeVar("T")


@runtime_checkable
class ParchiAckStore(ParchiStore, Protocol):
    """`ParchiStore` plus the one lookup creation needs to be idempotent.

    Kept as a separate protocol rather than added to `ParchiStore` so that adapters which do
    not implement the acknowledgement workflow are not forced to grow a method they will
    never be asked for.
    """

    def find_by_idempotency_key(self, idempotency_key: str) -> Parchi | None:
        """The parchi previously created under this key, or None. MUST NOT return a parchi
        whose `idempotency_key` differs."""
        ...

    def save_new(self, parchi: Parchi) -> None:
        """Persist a newly created parchi, refusing if its idempotency key is already taken.

        MUST be atomic with respect to `idempotency_key`: if two callers hold the same key,
        exactly one call to this method may succeed. Raises `DuplicateIdempotencyKey` for the
        loser, and the loser writes NOTHING.

        This is the point where "check then insert" becomes a single step. A caller that
        looks up the key, finds nothing, and then calls plain `save` is one scheduler tick
        away from two parches for one displaced worker; the check and the insert must not be
        separable. In a real adapter this is a conditional write on the key, not a lock.

        A parchi whose `idempotency_key` is None is not deduplicable and is stored plainly.
        """
        ...


@runtime_checkable
class AcknowledgementTokenStore(Protocol):
    """Storage for minted acknowledgement tokens. Holds hashes only."""

    def put(self, token: AcknowledgementToken) -> None: ...

    def get(self, token_hash: str) -> AcknowledgementToken | None: ...

    def consume(self, token_hash: str, *, at: datetime, event_id: str) -> AcknowledgementToken:
        """Mark a token used, permanently.

        MUST be a compare-and-set: if the token is already CONSUMED this MUST refuse rather
        than overwrite. Two concurrent confirmations racing on the same token is exactly the
        case this exists to make impossible, and the loser must lose here.
        """
        ...


@runtime_checkable
class IdempotencyLedger(Protocol):
    """Runs an operation at most once per key, and returns the FIRST result forever after.

    This is the idempotency mechanism for acknowledgement, and it is deliberately not
    "catch the duplicate-key error and carry on". That approach still runs the operation
    twice, so it still produces two acknowledgement events and two audit lines -- it just
    hides the second one. Here the second caller never runs the operation at all; it is
    handed the first caller's result.

    Implementations MUST make `execute_once` atomic with respect to `key`. The contract is:

      * `compute` is invoked at most once per key, ever
      * every later caller for that key receives the result of that one invocation
      * `compute` raising propagates to the caller that triggered it, and leaves the key
        unclaimed so a genuine retry can run

    Two concurrent callers therefore produce exactly one execution, and both observe the same
    outcome object.
    """

    def execute_once(self, *, key: str, compute: Callable[[], T]) -> T: ...
