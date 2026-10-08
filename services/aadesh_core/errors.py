"""Exceptions raised by the Aadesh core.

Each one marks a distinct kind of failure, because the right response differs: a corpus
integrity problem is an authoring bug to fix now, an authorization denial is a sentence to
show a user, and an illegal parchi transition is a programming error.
"""

from __future__ import annotations


class AadeshError(Exception):
    """Base class for every error the core raises."""


class CorpusIntegrityError(AadeshError):
    """The rules corpus is malformed in a way that cannot be safely interpreted.

    Raised rather than degraded, because guessing at the meaning of a corpus entry is
    exactly the behaviour Aadesh exists to avoid. A bad operator is an authoring bug.
    """


class IllegalParchiTransition(AadeshError):
    """An attempt to move a parchi through a transition its state machine forbids."""


class AuthorizationUnavailable(AadeshError):
    """The authorization provider could not reach a decision.

    Callers must fail closed. An authorization boundary that is unavailable is not an
    authorization boundary that permits.
    """


class ExplanationContractViolation(AadeshError):
    """Generated prose breached its output contract and must not be shown to a user."""


class TestOnlyComponentInProduction(AadeshError):
    """A component that is only safe in tests was constructed outside the test environment."""
