"""Core domain value objects.

Everything here is a frozen dataclass. Immutability is not stylistic: a parchi is evidence,
an obligation set is a point-in-time determination, and a citation is a claim about bytes on
disk. None of them should be mutable after construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from aadesh_core.domain.enums import ObligationStatus, Provenance, SourceState

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
    """

    stage: int
    order_doc_id: str
    order_sha256: str
    invoked_at: datetime


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

    @property
    def divergent(self) -> bool:
        """True only when both are known AND they disagree.

        An undeterminable implied stage is not a divergence; it is an absence. Reporting it
        as a conflict would manufacture an alarm out of missing corpus data.
        """
        if self.invoked is None or self.implied is None:
            return False
        if not self.implied.is_determinable:
            return False
        return self.invoked.stage != self.implied.stage


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
    field: str
    operator: str
    value: Any
    citation: Citation
    issues_parchi: bool
    worker_entitlement_ref: str | None = None
    source_state: SourceState = SourceState.UNSOURCED


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

    def fact(self, name: str) -> Any:
        return self.facts.get(name, _MISSING)

    def has_fact(self, name: str) -> bool:
        return name in self.facts


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


_MISSING = _Missing()
MISSING_FACT = _MISSING
"""Returned by SiteProfile.fact() when the key is absent entirely."""


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


@dataclass(frozen=True, slots=True)
class ExcludedObligation:
    """An obligation kept out of resolution, and why. Exclusion is reported, never silent."""

    obligation_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ObligationSet:
    """The full determination for one site at one moment."""

    site_id: str
    entity_type: str
    stage: InvokedStage | None
    results: tuple[ObligationResult, ...]
    excluded_unsourced: tuple[ExcludedObligation, ...]
    reading: StationReading | None
    resolved_at: datetime

    @property
    def provenance(self) -> Provenance | None:
        """Mirrors the reading's provenance so it cannot be dropped downstream."""
        return self.reading.provenance if self.reading is not None else None

    @property
    def applicable(self) -> tuple[ObligationResult, ...]:
        return tuple(r for r in self.results if r.status is ObligationStatus.MET)

    @property
    def unknown(self) -> tuple[ObligationResult, ...]:
        return tuple(r for r in self.results if r.status is ObligationStatus.UNKNOWN)

    @property
    def not_applicable(self) -> tuple[ObligationResult, ...]:
        return tuple(r for r in self.results if r.status is ObligationStatus.NOT_MET)

    @property
    def fully_sourced(self) -> bool:
        """False if any obligation was excluded for want of a verified citation.

        A set that is not fully sourced is not claim-ready, and callers should say so rather
        than present a partial corpus as a complete answer.
        """
        return not self.excluded_unsourced
