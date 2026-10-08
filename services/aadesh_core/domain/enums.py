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
    """Lifecycle of a worker's parchi.

    ```
    DRAFT --issue--> PENDING_ACK --acknowledge--> ACKNOWLEDGED --seal--> SEALED
      |                   |                             |
      +-------void--------+------------void-------------+--> VOID
    ```

    ACKNOWLEDGED and SEALED are separate states on purpose. ACKNOWLEDGED means a named
    worker has confirmed the halt that displaced them; SEALED means the record has been
    frozen over a content hash. Merging them would make "the worker confirmed it" and "the
    evidence was frozen" the same timestamp, and neither would then be independently
    auditable.

    SEALED and VOID are terminal -- no transition leaves them.
    """

    DRAFT = "draft"
    """Opened, not yet waiting on anybody."""

    PENDING_ACK = "pending_ack"
    """Issued and waiting on its named worker."""

    ACKNOWLEDGED = "acknowledged"
    """The named worker has explicitly confirmed it. Not yet frozen."""

    SEALED = "sealed"
    """Frozen over a content hash. Terminal. Immutable evidence."""

    VOID = "void"
    """Cancelled before sealing. Terminal."""


class AcknowledgementMethod(StrEnum):
    """HOW a worker confirmed a parchi.

    A closed vocabulary rather than free text, because this value ends up inside the sealed
    content hash: an acknowledgement that says only "confirmed, somehow" is not evidence of
    a method, and a free-text field would let a caller assert one that never happened.

    There is exactly one member today. It is here rather than as a bare string so the field
    is closed by construction, and adding a second mechanism is a visible, reviewable change
    that must also update the evidence schema.
    """

    QR_CONFIRMED = "qr_confirmed"
    """The worker resolved the opaque acknowledgement token and then took the explicit
    confirm action. NOTE: displaying a QR, or scanning one, is not this. The confirm action
    is what produces this value."""


class Role(StrEnum):
    """The three principal types. Adding a fourth is out of scope."""

    SUPERVISOR = "supervisor"
    WORKER = "worker"
    FACILITATOR = "facilitator"
