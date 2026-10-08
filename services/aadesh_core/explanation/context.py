"""The structured input the explanation model is allowed to see.

Aadesh's deterministic core already knows the answer. This module packages that answer -- and
nothing else -- into an explicit, reviewable input for the model, so the model's job is
strictly to *render* a decision rather than to reach one.

Two things are load-bearing here:

  * **The deterministic result is carried alongside, unchanged.** `ExplanationRequest` is
    derived FROM a `ResolutionResult` or a `Parchi`; it does not replace either. The caller
    keeps the authoritative object, so a model that disagrees changes nothing (see
    `service.py`).

  * **No personal data crosses the boundary.** The request holds site and record *references*
    -- opaque ids -- plus the stage/obligation/citation facts needed to explain a compliance
    decision. It deliberately omits the worker's id, name, phone, Aadhaar, bank details, PAN,
    home address and any raw acknowledgement token. `tests/unit/test_explanation_privacy.py`
    asserts the forbidden terms cannot appear in a payload.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from aadesh_core.domain import (
    Citation,
    InvokedStage,
    ObligationStatus,
    ResolutionMode,
    ResolutionResult,
)
from aadesh_core.domain.models import stage_name
from aadesh_core.explanation.contract import ExplanationContext
from aadesh_core.parchi import Parchi

SCHEMA_VERSION = "explanation/1"

DEFAULT_DISCLAIMER = (
    "This explanation restates a decision the deterministic Aadesh engine already reached. "
    "It is not legal advice, and the deterministic result is authoritative if the two differ."
)


class ExplanationKind(StrEnum):
    """The scenario an explanation answers. A closed vocabulary, so a caller cannot ask for an
    unmodelled one and have it silently rendered as something else."""

    OBLIGATION = "obligation"
    """Why this site has this obligation."""

    STAGE = "stage"
    """Why the official stage is what it is."""

    AQI_DISCREPANCY = "aqi_discrepancy"
    """AQI implies X but CAQM officially invoked Y."""

    HISTORICAL_REPLAY = "historical_replay"
    """This is a replay of a past invocation, not current state."""

    PARCHI = "parchi"
    """Why a Parchi is in a given lifecycle state."""

    UNKNOWN_FACT = "unknown_fact"
    """Why a condition could not be determined."""


@dataclass(frozen=True, slots=True)
class ExplanationCitation:
    """A citation the model is allowed to reference. The model may not invent one."""

    source_doc: str
    page: int
    quote: str
    label: str
    source_hash: str | None = None

    @classmethod
    def of(cls, citation: Citation, *, label: str) -> ExplanationCitation:
        return cls(
            source_doc=citation.source_doc,
            page=citation.page,
            quote=citation.quote,
            label=label,
            source_hash=citation.source_hash,
        )


@dataclass(frozen=True, slots=True)
class ExplanationFact:
    """One factual finding. `known=False` is UNKNOWN and must never be rendered as false."""

    name: str
    value: str
    known: bool = True


@dataclass(frozen=True, slots=True)
class ExplanationObligation:
    """The deterministic determination for one clause, as the model receives it."""

    obligation_id: str
    label: str
    status: str
    applicable: bool | None
    required_action: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExplanationRequest:
    """Everything the model may use, and nothing else.

    The fields the model might be tempted to change -- official stage, implied stage, replay
    status, obligation status, source citations and hashes -- are all present so the model can
    ECHO them, and so the grounding check can refuse a response that changes one.
    """

    context_id: str
    kind: ExplanationKind
    site_ref: str
    official_stage: str
    implied_stage: str
    stage_agreement: str
    stage_reason: str
    mode: str
    question: str | None = None
    replay_notice: str | None = None
    provenance: str | None = None
    obligations: tuple[ExplanationObligation, ...] = ()
    facts: tuple[ExplanationFact, ...] = ()
    citations: tuple[ExplanationCitation, ...] = ()
    parchi_ref: str | None = None
    parchi_status: str | None = None
    has_cited_amount: bool = False
    schema_version: str = SCHEMA_VERSION

    # -- deterministic inputs the contract check needs --------------------------

    def contract_context(self) -> ExplanationContext:
        """The contract context for the obligation-level check."""
        statuses: dict[str, ObligationStatus] = {}
        for obligation in self.obligations:
            try:
                statuses[obligation.obligation_id] = ObligationStatus(obligation.status)
            except ValueError:
                continue
        return ExplanationContext(
            allowed_clause_ids=frozenset(statuses),
            computed_statuses=MappingProxyType(statuses),
            has_cited_amount=self.has_cited_amount,
        )

    # -- citation grounding -----------------------------------------------------

    @property
    def allowed_citation_keys(self) -> frozenset[tuple[str, int]]:
        return frozenset((c.source_doc, c.page) for c in self.citations)

    @property
    def allowed_source_hashes(self) -> frozenset[str]:
        return frozenset(c.source_hash for c in self.citations if c.source_hash)

    # -- what actually gets sent ------------------------------------------------

    def to_prompt_payload(self) -> dict:
        """JSON-ready. This is the ONLY thing passed to the model."""
        return {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "kind": self.kind.value,
            "question": self.question,
            "site_ref": self.site_ref,
            "replay_status": self.mode,
            "official_stage": self.official_stage,
            "implied_stage": self.implied_stage,
            "stage_agreement": self.stage_agreement,
            "stage_reason": self.stage_reason,
            "replay_notice": self.replay_notice,
            "reading_provenance": self.provenance,
            "parchi_ref": self.parchi_ref,
            "parchi_status": self.parchi_status,
            "has_cited_amount": self.has_cited_amount,
            "obligations": [
                {
                    "obligation_id": o.obligation_id,
                    "label": o.label,
                    "status": o.status,
                    "applicable": o.applicable,
                    "required_action": o.required_action,
                    "reason": o.reason,
                }
                for o in self.obligations
            ],
            "facts": [{"name": f.name, "value": f.value, "known": f.known} for f in self.facts],
            "citations": [
                {
                    "source_doc": c.source_doc,
                    "page": c.page,
                    "quote": c.quote,
                    "label": c.label,
                    "source_hash": c.source_hash,
                }
                for c in self.citations
            ],
        }


def _stage_display(stage: int | None) -> str:
    return stage_name(stage)


def _replay_status(result: ResolutionResult) -> str:
    return "REPLAY" if result.mode is ResolutionMode.REPLAY else "CURRENT"


def _default_kind(result: ResolutionResult) -> ExplanationKind:
    if result.mode is ResolutionMode.REPLAY:
        return ExplanationKind.HISTORICAL_REPLAY
    if result.stage_status.divergent:
        return ExplanationKind.AQI_DISCREPANCY
    if result.unknown:
        return ExplanationKind.UNKNOWN_FACT
    return ExplanationKind.STAGE


def request_for_resolution(
    result: ResolutionResult,
    *,
    kind: ExplanationKind | None = None,
    question: str | None = None,
    facts: Iterable[ExplanationFact] = (),
    context_id: str | None = None,
) -> ExplanationRequest:
    """Package a resolved obligation set for explanation. Carries its citations, never the site."""
    chosen = kind or _default_kind(result)
    obligations = tuple(
        ExplanationObligation(
            obligation_id=r.obligation_id,
            label=r.label,
            status=r.status.value,
            applicable=r.applicable,
            required_action=r.required_action,
            reason=r.reason,
        )
        for r in result.results
    )
    citations: dict[tuple[str, int, str], ExplanationCitation] = {}
    for r in result.results:
        key = (r.citation.source_doc, r.citation.page, r.citation.quote)
        citations.setdefault(key, ExplanationCitation.of(r.citation, label=r.obligation_id))
    if result.stage is not None and result.stage.citation is not None:
        citation = result.stage.citation
        key = (citation.source_doc, citation.page, citation.quote)
        citations.setdefault(key, ExplanationCitation.of(citation, label="official_invocation"))
    return ExplanationRequest(
        context_id=context_id or f"expl-{chosen.value}-{result.site_id}",
        kind=chosen,
        site_ref=result.site_id,
        official_stage=_stage_display(result.stage_status.official_stage),
        implied_stage=_stage_display(result.stage_status.implied_stage),
        stage_agreement=result.stage_status.status.value,
        stage_reason=result.stage_status.reason,
        mode=_replay_status(result),
        question=question,
        replay_notice=result.replay_notice,
        provenance=result.provenance.value if result.provenance is not None else None,
        obligations=obligations,
        facts=tuple(facts),
        citations=tuple(citations.values()),
        has_cited_amount=False,
    )


def request_for_parchi(
    parchi: Parchi,
    *,
    question: str | None = None,
    context_id: str | None = None,
) -> ExplanationRequest:
    """Package a Parchi's lifecycle state for explanation.

    The request carries the Parchi's OPAQUE reference and state, the stage that displaced the
    worker, and the stage order's citation. It deliberately carries no worker identity and no
    acknowledgement token -- the raw token is not representable on the record to begin with,
    and the worker's id is unnecessary to explain a lifecycle state.
    """
    stage: InvokedStage | None = parchi.stage
    citations: tuple[ExplanationCitation, ...] = ()
    if stage is not None and stage.citation is not None:
        citations = (ExplanationCitation.of(stage.citation, label="official_invocation"),)
    return ExplanationRequest(
        context_id=context_id or f"expl-{ExplanationKind.PARCHI.value}-{parchi.parchi_id}",
        kind=ExplanationKind.PARCHI,
        site_ref=parchi.site_id,
        official_stage=_stage_display(stage.stage if stage is not None else None),
        implied_stage=_stage_display(None),
        stage_agreement="PARCHI",
        stage_reason=_parchi_stage_reason(parchi),
        mode="CURRENT",
        question=question,
        replay_notice=None,
        provenance=parchi.provenance.value if parchi.provenance is not None else None,
        obligations=(),
        facts=(),
        citations=citations,
        parchi_ref=parchi.parchi_id,
        parchi_status=parchi.state.value,
        has_cited_amount=False,
    )


def _parchi_stage_reason(parchi: Parchi) -> str:
    if parchi.stage is None:
        return "This Parchi is not tied to a current official GRAP invocation."
    return (
        f"Opened against the official invocation of {stage_name(parchi.stage.stage)} "
        f"(order {parchi.stage.order_doc_id})."
    )


__all__ = [
    "DEFAULT_DISCLAIMER",
    "SCHEMA_VERSION",
    "ExplanationCitation",
    "ExplanationFact",
    "ExplanationKind",
    "ExplanationObligation",
    "ExplanationRequest",
    "request_for_parchi",
    "request_for_resolution",
]
