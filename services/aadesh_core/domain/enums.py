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
    """Compliance with one applicable cited requirement, based on recorded facts only."""

    MET = "met"
    """Known facts satisfy the applicable requirement."""

    NOT_MET = "not_met"
    """Known facts establish a violation of the applicable requirement."""

    UNKNOWN = "unknown"
    """Applicability or compliance cannot be determined. Never inferred as a violation."""

    NOT_APPLICABLE = "not_applicable"
    """The verified stage or known site facts put this requirement out of scope."""


class ResolutionMode(StrEnum):
    CURRENT = "CURRENT"
    REPLAY = "REPLAY"


class StageAgreement(StrEnum):
    ALIGNED = "ALIGNED"
    DISCREPANCY = "DISCREPANCY"
    OFFICIAL_ONLY = "OFFICIAL_ONLY"
    NO_OFFICIAL_INVOCATION = "NO_OFFICIAL_INVOCATION"


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


class StandingOrderStatus(StrEnum):
    """Lifecycle of a signed, time-bounded standing order.

    Transitions are pure functions of the current order and explicit actions; expiry is
    computed from the clock at evaluation time, not written by a sweeper. See
    `aadesh_core.standing_order.lifecycle.project_status`.
    """

    DRAFT = "draft"
    """Written but not yet signed by the named supervisor. May be edited freely."""

    CONFIRMED = "confirmed"
    """Signed by the supervisor. commitment_hash is now fixed over the signed fields."""

    ACTIVE = "active"
    """now >= valid_from and now < valid_until. Eligible to be triggered by its trigger."""

    TRIGGERED = "triggered"
    """A trigger event matched this order and the machine was started."""

    COMPLETED = "completed"
    """The machine reached Audit and reported its outcome."""

    EXPIRED = "expired"
    """now >= valid_until. Reachable from any non-terminal status; the only closure that a
    timer would have provided, but computed on demand rather than by a frontend timer."""


class StandingOrderAction(StrEnum):
    """The closed action vocabulary a standing order may pre-commit to.

    Exactly two, matching the product example: a dust-work halt and one parchi per rostered
    worker. Nothing speculative. A standing order is not a general autonomous-agent permission,
    and the schema's additionalProperties: false plus this closed enum are what make that
    claim testable.
    """

    ISSUE_HALT = "issue_halt"
    """Issue the dust-work halt for the order's site."""

    OPEN_PARCHI_PER_WORKER = "open_parchi_per_worker"
    """Open one DRAFT parchi for each rostered worker on the order's site."""


class TriggerType(StrEnum):
    """What kind of event may trigger a standing order.

    A single member on purpose. An unknown trigger type is refused rather than silently read
    as a stage trigger, because a StandingOrder carries no field that could carry a prompt,
    instruction, script or arbitrary agent instruction.
    """

    OFFICIAL_STAGE_INVOCATION = "official_stage_invocation"
    """The currently invoked GRAP stage, as proved by the corpus, matched the order's trigger."""


class StageMatch(StrEnum):
    """How strictly the trigger's stage must match the invoked stage.

    The corpus's own rule (lower-stage obligations continue at higher stages) is made explicit
    here as a per-order choice the supervisor signs. EXACT requires the invoked stage to equal
    the trigger stage; AT_OR_ABOVE fires when the invoked stage is >= the trigger stage.
    """

    EXACT = "exact"
    """The invoked stage must equal the trigger stage."""

    AT_OR_ABOVE = "at_or_above"
    """The invoked stage must be >= the trigger stage, mirroring the corpus continuation rule."""
