"""Deterministic explanation. Always correct, always available, never optional.

Every user-facing sentence Aadesh needs can be produced here, without a model and without a
network. The Bedrock/Strands layer is a rephrasing of these sentences, and when it is absent
or breaches its contract these are what the user sees.
"""

from __future__ import annotations

from aadesh_core.domain import ObligationResult, ObligationSet, ObligationStatus
from aadesh_core.explanation.contract import Explanation, ExplanationClaim, ExplanationContext

_STATUS_SENTENCE = {
    ObligationStatus.MET: "applies to this site",
    ObligationStatus.NOT_MET: "does not apply to this site",
    ObligationStatus.UNKNOWN: "cannot be determined for this site",
}


def context_for(
    obligation_set: ObligationSet, *, has_cited_amount: bool = False
) -> ExplanationContext:
    """Build the contract context from a resolved obligation set."""
    return ExplanationContext(
        allowed_clause_ids=frozenset(r.obligation_id for r in obligation_set.results),
        computed_statuses={r.obligation_id: r.status for r in obligation_set.results},
        has_cited_amount=has_cited_amount,
    )


def explain_result(result: ObligationResult) -> Explanation:
    """One obligation, in plain language, phrased as applicability and never as permission."""
    text = (
        f"{result.label} {_STATUS_SENTENCE[result.status]}. "
        f"{result.reason} "
        f"Source: {result.citation.source_doc}, page {result.citation.page}."
    )
    return Explanation(
        text=text,
        claims=(ExplanationClaim(result.obligation_id, result.status),),
        source="deterministic",
    )


def explain_set(obligation_set: ObligationSet) -> Explanation:
    """The whole determination, including what could not be determined and what was excluded."""
    lines: list[str] = []

    if obligation_set.stage is None:
        lines.append(
            "No GRAP stage is invoked by any CAQM order in the corpus, so no obligation "
            "can be determined."
        )
    else:
        lines.append(
            f"Stage {obligation_set.stage.stage} is invoked by order "
            f"{obligation_set.stage.order_doc_id} "
            f"(sha256 {obligation_set.stage.order_sha256[:12]}...)."
        )

    applicable = obligation_set.applicable
    unknown = obligation_set.unknown
    lines.append(f"{len(applicable)} obligation(s) apply to this site.")
    if unknown:
        lines.append(
            f"{len(unknown)} could not be determined because a site fact is missing or "
            f"unknown. These are not treated as inapplicable."
        )
    if obligation_set.excluded_unsourced:
        lines.append(
            f"{len(obligation_set.excluded_unsourced)} clause(s) were excluded because "
            f"their citations are not verified against hashed source bytes."
        )
    if obligation_set.provenance is not None and obligation_set.provenance != "measured":
        lines.append(
            f"The station reading behind this determination is {obligation_set.provenance.value}, "
            f"not a live measurement."
        )

    return Explanation(
        text=" ".join(lines),
        claims=tuple(ExplanationClaim(r.obligation_id, r.status) for r in obligation_set.results),
        source="deterministic",
    )
