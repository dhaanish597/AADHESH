"""Core domain value objects.

Everything here is a frozen dataclass. Immutability is not stylistic: a parchi is evidence,
an obligation set is a point-in-time determination, and a citation is a claim about bytes on
disk. None of them should be mutable after construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any

from aadesh_core.domain.enums import (
    InvocationLifecycle,
    ObligationStatus,
    Provenance,
    ResolutionMode,
    SourceState,
    StageAgreement,
)
from aadesh_core.domain.facts import MISSING_FACT
from aadesh_core.domain.predicates import Predicate

CONSTRUCTION_SITE = "construction_site"
"""The only entity type in scope. Deliberately a single value."""


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Citation:
    """A pointer into a hashed source document, plus the verbatim text being relied on.

    `quote` must appear byte-for-byte in the extracted text of `page`. `make verify`
    re-checks exactly that. A paraphrase fails, which is the point.
    """

    source_doc: str
    page: int
    quote: str
    source_hash: str | None = None


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Provenance record for one authoritative document."""

    doc_id: str
    title: str
    publisher: str
    source_url: str
    retrieved_at: datetime
    sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class StationReading:
    """One reading from one monitoring station.

    `observed_at` is when the station measured; `ingested_at` is when Aadesh saw it. Both are
    kept because the gap is the honest answer to "how fresh is this?" -- CPCB station data is
    hourly, and calling it real-time would be a lie.
    """

    station_id: str
    parameter: str
    value: float
    observed_at: datetime
    ingested_at: datetime
    provenance: Provenance

    def age(self, now: datetime) -> timedelta:
        return now - self.observed_at

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        return self.age(now) > max_age


# ---------------------------------------------------------------------------
# Stage: invoked vs implied, never conflated
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InvokedStage:
    """A GRAP stage that a CAQM order has actually invoked.

    This is the authoritative stage. It carries the hash of the order that invoked it, so
    any downstream claim can be traced to specific bytes. CAQM may invoke pre-emptively on a
    forecast or hold off despite a high reading, which is exactly why this is not computed
    from an AQI number.

    `lifecycle` distinguishes the CURRENT official state from a HISTORICAL one. A revoked
    invocation is evidence about the past, not a stage in force, so `is_current` is False for
    it and the loader refuses to hand it to the resolver as the live stage. The revocation
    itself is cited (`revocation_citation`), so "it was revoked" is provable rather than
    asserted -- the same rule every other fact in this corpus obeys.
    """

    stage: int
    order_doc_id: str
    order_sha256: str
    invoked_at: datetime
    lifecycle: InvocationLifecycle = InvocationLifecycle.ACTIVE
    revoked_at: datetime | None = None
    revocation_citation: Citation | None = None
    citation: Citation | None = None
    source_state: SourceState = SourceState.UNSOURCED

    @property
    def is_current(self) -> bool:
        """True only for a stage presently in force. A revoked invocation is history."""
        return (
            self.lifecycle is InvocationLifecycle.ACTIVE
            and self.revoked_at is None
            and self.revocation_citation is None
        )

    def describe(self) -> str:
        """A single honest sentence about what this record is.

        The distinction this makes is the entire reason the lifecycle exists: without it,
        January's revoked Stage III and a live Stage III read identically on screen.
        """
        when = self.invoked_at.date().isoformat()
        if self.is_current:
            return f"Current: CAQM invoked Stage {self.stage} on {when}."
        revoked = f", revoked {self.revoked_at.date().isoformat()}" if self.revoked_at else ""
        return (
            f"Historical replay: CAQM invoked Stage {self.stage} on {when}{revoked}. "
            f"This stage is not currently in force."
        )


@dataclass(frozen=True, slots=True)
class ImpliedStage:
    """A stage inferred from a station reading via CITED threshold bands.

    Never authoritative, and never available until `corpus/stage_bands/` is populated from a
    hashed order. `stage is None` means the bands are not sourced yet, which is the honest
    Day 1 answer rather than a guess.
    """

    stage: int | None
    citation: Citation | None
    reading: StationReading | None

    @property
    def is_determinable(self) -> bool:
        return self.stage is not None


@dataclass(frozen=True, slots=True)
class StageStatus:
    """What Aadesh shows on its single status line."""

    invoked: InvokedStage | None
    implied: ImpliedStage | None
    mode: ResolutionMode = ResolutionMode.CURRENT

    @property
    def official_stage(self) -> int | None:
        return self.invoked.stage if self.invoked is not None else None

    @property
    def implied_stage(self) -> int | None:
        return self.implied.stage if self.implied is not None else None

    @property
    def status(self) -> StageAgreement:
        if self.implied_stage is not None:
            if self.implied_stage != self.official_stage:
                return StageAgreement.DISCREPANCY
            return StageAgreement.ALIGNED
        if self.official_stage is not None:
            return StageAgreement.OFFICIAL_ONLY
        return StageAgreement.NO_OFFICIAL_INVOCATION

    @property
    def reason(self) -> str:
        official = "historical" if self.mode is ResolutionMode.REPLAY else "current"
        if self.status is StageAgreement.DISCREPANCY:
            observed = f"Observed AQI implies {stage_name(self.implied_stage)}, but "
            if self.official_stage is None:
                return observed + f"no verified {official} CAQM invocation is present."
            return (
                observed
                + f"the verified {official} CAQM invocation is {stage_name(self.official_stage)}. "
                "Aadesh does not infer legal activation from AQI. "
                "Obligations are evaluated against the verified official invocation."
            )
        if self.official_stage is None:
            return f"No verified {official} CAQM invocation is present."
        if self.status is StageAgreement.ALIGNED:
            return f"Observed AQI and the verified {official} invocation agree."
        return (
            f"The verified {official} invocation is {stage_name(self.official_stage)}; "
            "an implied AQI stage is not determinable."
        )

    @property
    def divergent(self) -> bool:
        return self.status is StageAgreement.DISCREPANCY


def stage_name(stage: int | None) -> str:
    """Presentation only; no activation or threshold semantics."""
    ordinals = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
    if stage is None:
        return "NONE"
    return f"Stage {ordinals[stage] if 0 < stage < len(ordinals) else stage}"


# ---------------------------------------------------------------------------
# Rules as data
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Obligation:
    """One obligation a GRAP stage places on one entity type.

    `source_state` defaults to UNSOURCED so that an obligation which never passed through
    verification is excluded from resolution. Forgetting to set it fails safe.
    """

    obligation_id: str
    entity_types: tuple[str, ...]
    triggers_at_stage: int
    label: str
    applicability: Predicate
    requirement: Predicate
    required_action: str
    citation: Citation
    issues_parchi: bool
    evidence: tuple[tuple[str, Citation], ...]
    stage_evidence: str
    continuation_evidence: str
    action_evidence: tuple[str, ...]
    clarification_when: Predicate | None = None
    clarification: str | None = None
    worker_entitlement_ref: str | None = None
    source_state: SourceState = SourceState.UNSOURCED

    @property
    def citations(self) -> tuple[Citation, ...]:
        return (self.citation, *(citation for _, citation in self.evidence))


@dataclass(frozen=True, slots=True)
class VerifiedCorpus:
    """An immutable verification snapshot supplied by a trusted corpus adapter.

    The proof receipts bind complete rules, bands and invocations as well as their exact
    quotes, pages, documents and source hashes. Setting a source_state flag alone does not
    admit an object to resolution.
    Reusing a snapshot intentionally replays those bytes; obtain a fresh snapshot for each
    new production resolution so filesystem changes are re-proved.
    """

    obligations: tuple[Obligation, ...]
    stage_bands: tuple[StageBand, ...]
    invocations: tuple[InvokedStage, ...]
    proved_citations: frozenset[Citation]
    proved_obligations: frozenset[Obligation] = frozenset()
    proved_invocations: frozenset[InvokedStage] = frozenset()
    proved_stage_bands: frozenset[StageBand] = frozenset()


@dataclass(frozen=True, slots=True)
class ReplayContext:
    invocation_date: str
    revocation_date: str
    at: datetime | None = None

    def __post_init__(self) -> None:
        start = date.fromisoformat(self.invocation_date)
        end = date.fromisoformat(self.revocation_date)
        if start >= end:
            raise ValueError("Replay invocation_date must precede revocation_date")
        if self.at is not None and self.at.utcoffset() is None:
            raise ValueError("Replay at must include a timezone")


@dataclass(frozen=True, slots=True)
class EntitlementAmount:
    """A monetary figure that appears in a hashed source document.

    `basis` is required so the UI can never multiply a one-time figure by a number of days.
    """

    value_inr: float
    basis: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class Entitlement:
    """A cited clause describing what a displaced worker may be entitled to.

    `amount` is None unless a figure is stated in a hashed source. When it is None, Aadesh
    reports displaced worker-days instead, which is always provable.
    """

    entitlement_id: str
    label: str
    citation: Citation
    amount: EntitlementAmount | None = None
    readiness_requirements: tuple[tuple[str, Citation], ...] = ()
    source_state: SourceState = SourceState.UNSOURCED

    @property
    def has_cited_amount(self) -> bool:
        return self.amount is not None


@dataclass(frozen=True, slots=True)
class StageBand:
    """A cited AQI range that implies a GRAP stage. The only home for these thresholds."""

    stage: int
    pollutant: str
    aqi_lower: float
    aqi_upper: float | None
    citation: Citation
    source_state: SourceState = SourceState.UNSOURCED
    aqi_lower_inclusive: bool = True


# ---------------------------------------------------------------------------
# Site and people
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SiteProfile:
    """The facts about one construction site that obligations key on.

    A fact that is absent from `facts`, or present as UNKNOWN_FACT, resolves to UNKNOWN.
    """

    site_id: str
    entity_type: str
    nearest_station_id: str
    facts: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))

    def fact(self, name: str) -> Any:
        return self.facts.get(name, MISSING_FACT)

    def has_fact(self, name: str) -> bool:
        return name in self.facts


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated actor. Maps onto a Cedar principal entity."""

    principal_id: str
    role: str
    assigned_site: str | None = None


@dataclass(frozen=True, slots=True)
class Worker:
    """A rostered worker. `registration_number` is None when unregistered or unknown --
    which is the common case, and the readiness checklist exists to surface it."""

    worker_id: str
    display_name: str
    site_id: str
    registration_number: str | None = None


# ---------------------------------------------------------------------------
# Resolution output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObligationResult:
    """The determination for one obligation, with the reason stated in words.

    `reason` exists so a denial or an unknown is explainable without a model. The
    deterministic path must be able to produce every user-facing sentence by itself.
    """

    obligation_id: str
    status: ObligationStatus
    label: str
    citation: Citation
    reason: str
    issues_parchi: bool
    worker_entitlement_ref: str | None = None
    applicable: bool | None = None
    required_action: str = ""
    evidence: tuple[Citation, ...] = ()
    mode: ResolutionMode = ResolutionMode.CURRENT

    @property
    def source_doc(self) -> str:
        return self.citation.source_doc

    @property
    def source_page(self) -> int:
        return self.citation.page

    @property
    def source_quote(self) -> str:
        return self.citation.quote

    @property
    def source_hash(self) -> str | None:
        return self.citation.source_hash


@dataclass(frozen=True, slots=True)
class ExcludedObligation:
    """An obligation kept out of resolution, and why. Exclusion is reported, never silent."""

    obligation_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """The full determination for one site at one moment."""

    site_id: str
    entity_type: str
    stage: InvokedStage | None
    results: tuple[ObligationResult, ...]
    excluded_unsourced: tuple[ExcludedObligation, ...]
    reading: StationReading | None
    resolved_at: datetime
    stage_status: StageStatus
    mode: ResolutionMode = ResolutionMode.CURRENT
    replay_context: ReplayContext | None = None
    replay_notice: str | None = None
    current_stage: InvokedStage | None = None

    @property
    def provenance(self) -> Provenance | None:
        """Mirrors the reading's provenance so it cannot be dropped downstream."""
        return self.reading.provenance if self.reading is not None else None

    @property
    def applicable(self) -> tuple[ObligationResult, ...]:
        return tuple(r for r in self.results if r.applicable is True)

    @property
    def unknown(self) -> tuple[ObligationResult, ...]:
        return tuple(r for r in self.results if r.status is ObligationStatus.UNKNOWN)

    @property
    def not_applicable(self) -> tuple[ObligationResult, ...]:
        return tuple(r for r in self.results if r.status is ObligationStatus.NOT_APPLICABLE)

    @property
    def fully_sourced(self) -> bool:
        """False if any obligation was excluded for want of a verified citation.

        A set that is not fully sourced is not claim-ready, and callers should say so rather
        than present a partial corpus as a complete answer.
        """
        return not self.excluded_unsourced


# Existing integrations consume the same result object; status now describes compliance.
ObligationSet = ResolutionResult
