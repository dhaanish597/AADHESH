"""Enumerations for the Aadesh domain."""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    """Where a station reading came from.

    Carried on every reading and propagated into every obligation set and parchi, so a
    placeholder can never be silently presented as a measurement. There is deliberately no
    default: a reading must say what it is.
    """

    MEASURED = "measured"
    """A live reading from a monitoring station, via OpenAQ, attributed to CPCB."""

    SYNTHETIC = "synthetic"
    """A placeholder. Not a measurement of anything. Must be labelled wherever shown."""

    REPLAY = "replay"
    """A previously recorded real reading, replayed. Real, but not current."""


class InvocationLifecycle(StrEnum):
    """Whether an invoked GRAP stage is currently in force or has been revoked.

    A stage is invoked by a CAQM order and, crucially, can be revoked by a later one. Without
    this distinction the corpus cannot tell the CURRENT official state apart from a HISTORICAL
    invocation, and January's Stage III would silently keep enforcing in October. The loader
    therefore treats only ACTIVE as "currently invoked"; a REVOKED invocation is retained as
    replay evidence and never fed to the resolver as if it were live.
    """

    ACTIVE = "active"
    """In force. A CAQM order invoked this stage and nothing has revoked it."""

    REVOKED = "revoked"
    """Superseded by a later order. Kept as historical/replay evidence, never current."""


class SourceState(StrEnum):
    """Whether a corpus entry's quote has been proved against hashed source bytes."""

    VERIFIED = "verified"
    """`make verify` found this quote verbatim in the page it cites."""

    UNSOURCED = "unsourced"
    """Not proved. Excluded from resolution. The default, so forgetting fails safe."""


class ObligationStatus(StrEnum):
    """The outcome of evaluating one obligation against one site profile.

    Note carefully what MET and NOT_MET mean here. They describe whether the obligation's
    trigger condition is satisfied -- that is, whether the obligation APPLIES to this site --
    not whether the site is in compliance. Aadesh never judges compliance; it says which
    clauses apply and cites them.
    """

    MET = "met"
    """The trigger condition holds. This obligation applies to this site at this stage."""

    NOT_MET = "not_met"
    """The trigger condition was evaluated and does not hold. Known, not assumed."""

    UNKNOWN = "unknown"
    """A fact needed to decide is missing or itself unknown. Never inferred as NOT_MET."""


class ParchiState(StrEnum):
    """Lifecycle of a worker's parchi."""

    DRAFT = "draft"
    PENDING_ACK = "pending_ack"
    SEALED = "sealed"
    VOID = "void"


class Role(StrEnum):
    """The three principal types. Adding a fourth is out of scope."""

    SUPERVISOR = "supervisor"
    WORKER = "worker"
    FACILITATOR = "facilitator"
