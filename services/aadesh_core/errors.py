"""Exceptions raised by the Aadesh core.

Each one marks a distinct kind of failure, because the right response differs: a corpus
integrity problem is an authoring bug to fix now, an authorization denial is a sentence to
show a user, and an illegal parchi transition is a programming error.
"""

from __future__ import annotations

from enum import StrEnum


class AadeshError(Exception):
    """Base class for every error the core raises."""


class CorpusIntegrityError(AadeshError):
    """The rules corpus is malformed in a way that cannot be safely interpreted.

    Raised rather than degraded, because guessing at the meaning of a corpus entry is
    exactly the behaviour Aadesh exists to avoid. A bad operator is an authoring bug.
    """


class IllegalParchiTransition(AadeshError):
    """An attempt to move a parchi through a transition its state machine forbids."""


class AcknowledgementRejected(AadeshError):
    """A worker acknowledgement was refused, and no state changed.

    Every subclass MUST carry a `message` that is identical across all rejections of the same
    kind. An acknowledgement endpoint that distinguishes "no such token" from "expired token"
    tells a prober which of their guesses was close, so the reason is modelled separately
    from the sentence.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TokenRejectionReason(StrEnum):
    """Why a token was refused. Domain-facing only -- never render this to a user.

    UNKNOWN covers both "we have never issued that token" and "that token is not ours".
    Those are deliberately the same reason: keeping them apart would let anyone holding a
    forged token learn that it was forged rather than expired.
    """

    MALFORMED = "malformed"
    """Not an `aadesh://ack/<token>` payload at all."""

    UNKNOWN = "unknown"
    """Well-formed, but no token we issued. Includes forged tokens."""

    EXPIRED = "expired"
    """Ours, but past its expiry."""

    CONSUMED = "consumed"
    """Ours, and already used. Only reachable by a replay."""


class TokenRejected(AcknowledgementRejected):
    """The presented acknowledgement token could not be used.

    `reason` is for the domain and for tests; `message` is the single generic sentence that
    is safe to show a caller.
    """

    def __init__(self, reason: TokenRejectionReason) -> None:
        self.reason = reason
        super().__init__("This acknowledgement link is not valid. Ask for a new one.")


class WrongWorker(AcknowledgementRejected):
    """The acting principal is not the worker named on the parchi.

    A supervisor cannot acknowledge on a worker's behalf merely because they opened the
    workflow, and neither can another worker.
    """

    def __init__(self, parchi_id: str) -> None:
        self.parchi_id = parchi_id
        super().__init__("This parchi can only be acknowledged by the worker named on it.")


class DuplicateIdempotencyKey(AadeshError):
    """A record already exists for this idempotency key, and the new one was NOT written.

    Raised by an atomic conditional create. This is a normal outcome of two callers racing,
    not a fault: the caller reads back the record that won and returns it. It is deliberately
    distinct from "something went wrong", because the correct response is different -- do not
    retry, do not report failure, return the existing record.
    """

    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(
            f"A record already exists for idempotency key {idempotency_key!r}. "
            f"The duplicate write was refused."
        )


class AuthorizationUnavailable(AadeshError):
    """The authorization provider could not reach a decision.

    Callers must fail closed. An authorization boundary that is unavailable is not an
    authorization boundary that permits.
    """


class ExplanationContractViolation(AadeshError):
    """Generated prose breached its output contract and must not be shown to a user."""


class TestOnlyComponentInProduction(AadeshError):
    """A component that is only safe in tests was constructed outside the test environment."""

    # The leading "Test" makes pytest try to collect this as a test class. Keep the name --
    # it is the clearest description of the failure -- and opt out of collection instead.
    __test__ = False
