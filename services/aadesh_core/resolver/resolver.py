"""The deterministic obligation resolver.

This function is the heart of Aadesh and it is deliberately boring: a pure function over
plain data, with no clock read, no network call, no I/O, and no model anywhere near it. Same
inputs, same outputs, always. That is what makes the result something you can put in front of
a worker and defend afterwards.

Order of checks matters and is load-bearing:

  1. **Entity scope** -- an obligation for another entity type is out of scope, full stop.
  2. **Source state** -- an unverified citation is excluded BEFORE evaluation, so unproven
     text can never produce a determination.
  3. **Invoked stage** -- absent means unknown, not "nothing applies".
  4. **Stage trigger** -- an obligation above the invoked stage genuinely does not apply.
  5. **Fact evaluation** -- missing or unknown facts yield UNKNOWN.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from aadesh_core.domain import (
    MISSING_FACT,
    UNKNOWN_FACT,
    ExcludedObligation,
    InvokedStage,
    Obligation,
    ObligationResult,
    ObligationSet,
    ObligationStatus,
    SiteProfile,
    SourceState,
    StationReading,
)
from aadesh_core.resolver.operators import apply_operator


def _unsourced_reason(obligation: Obligation) -> str:
    return (
        f"Citation for {obligation.obligation_id} is not verified against hashed source "
        f"bytes (cites {obligation.citation.source_doc} p.{obligation.citation.page}). "
        f"Excluded from resolution. Run `make verify` for detail."
    )


def _evaluate(obligation: Obligation, site: SiteProfile) -> tuple[ObligationStatus, str]:
    """Evaluate one obligation's trigger condition against the site profile."""
    raw = site.fact(obligation.field)

    if raw is MISSING_FACT:
        return (
            ObligationStatus.UNKNOWN,
            f"Site fact {obligation.field!r} is not recorded for site {site.site_id}, "
            f"so whether this obligation applies cannot be determined.",
        )

    if raw is UNKNOWN_FACT:
        return (
            ObligationStatus.UNKNOWN,
            f"Site fact {obligation.field!r} is recorded as unknown, "
            f"so whether this obligation applies cannot be determined.",
        )

    try:
        holds = apply_operator(obligation.operator, raw, obligation.value)
    except TypeError:
        # A type mismatch is a corpus authoring slip. Degrade to UNKNOWN rather than take
        # the resolver down mid-halt, but say plainly that the comparison was impossible.
        return (
            ObligationStatus.UNKNOWN,
            f"Cannot compare site fact {obligation.field!r} "
            f"({type(raw).__name__}) using operator {obligation.operator!r} against "
            f"{obligation.value!r} ({type(obligation.value).__name__}). "
            f"Treated as unknown.",
        )

    if holds:
        return (
            ObligationStatus.MET,
            f"Site fact {obligation.field!r} satisfies "
            f"{obligation.operator} {obligation.value!r}, so this obligation applies.",
        )
    return (
        ObligationStatus.NOT_MET,
        f"Site fact {obligation.field!r} does not satisfy "
        f"{obligation.operator} {obligation.value!r}, so this obligation does not apply.",
    )


def resolve_obligations(
    *,
    site: SiteProfile,
    stage: InvokedStage | None,
    obligations: Sequence[Obligation],
    reading: StationReading | None,
    now: datetime,
) -> ObligationSet:
    """Resolve `obligations` against `site` for the given invoked `stage`.

    `now` is injected rather than read, so resolution is reproducible. `reading` does not
    affect any determination -- the stage comes from an order, not from arithmetic on an AQI
    number -- but it is carried into the result so its provenance travels with the record.
    """
    results: list[ObligationResult] = []
    excluded: list[ExcludedObligation] = []

    for obligation in obligations:
        if site.entity_type not in obligation.entity_types:
            continue

        if obligation.source_state is not SourceState.VERIFIED:
            excluded.append(
                ExcludedObligation(
                    obligation_id=obligation.obligation_id,
                    reason=_unsourced_reason(obligation),
                )
            )
            continue

        if stage is None:
            status = ObligationStatus.UNKNOWN
            reason = (
                "No GRAP stage has been invoked by a CAQM order in the corpus, so whether "
                "this obligation applies cannot be determined."
            )
        elif obligation.triggers_at_stage > stage.stage:
            status = ObligationStatus.NOT_MET
            reason = (
                f"Obligation triggers at stage {obligation.triggers_at_stage}; "
                f"stage {stage.stage} is invoked, so it does not apply."
            )
        else:
            status, reason = _evaluate(obligation, site)

        results.append(
            ObligationResult(
                obligation_id=obligation.obligation_id,
                status=status,
                label=obligation.label,
                citation=obligation.citation,
                reason=reason,
                issues_parchi=obligation.issues_parchi,
                worker_entitlement_ref=obligation.worker_entitlement_ref,
            )
        )

    return ObligationSet(
        site_id=site.site_id,
        entity_type=site.entity_type,
        stage=stage,
        results=tuple(results),
        excluded_unsourced=tuple(excluded),
        reading=reading,
        resolved_at=now,
    )
