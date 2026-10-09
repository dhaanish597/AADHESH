"""Pure obligation resolution over an immutable, verified corpus snapshot.

No I/O, clock reads, model calls, rule IDs, project categories or legal thresholds here.
Applicability and compliance are separate expressions supplied by the cited corpus.
"""

from __future__ import annotations

import re
from datetime import datetime

from aadesh_core.citations import literal_is_cited, quote_names_stage
from aadesh_core.domain import (
    Citation,
    ConstructionSite,
    ExcludedObligation,
    InvocationLifecycle,
    InvokedStage,
    Obligation,
    ObligationResult,
    ObligationStatus,
    ReplayContext,
    ResolutionMode,
    ResolutionResult,
    SiteProfile,
    SourceState,
    StationReading,
    VerifiedCorpus,
)
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.resolver.predicates import evaluate
from aadesh_core.stages import stage_status


def _proved(citation: Citation | None, corpus: VerifiedCorpus) -> bool:
    return (
        isinstance(citation, Citation)
        and bool(citation.source_doc and citation.quote.strip())
        and type(citation.page) is int
        and citation.page > 0
        and citation.source_hash is not None
        and re.fullmatch(r"[a-f0-9]{64}", citation.source_hash) is not None
        and citation in corpus.proved_citations
    )


def _rule_proved(rule: Obligation, corpus: VerifiedCorpus) -> bool:
    if rule.source_state is not SourceState.VERIFIED or rule not in corpus.proved_obligations:
        return False
    if not all(_proved(citation, corpus) for citation in rule.citations):
        return False
    evidence = {"clause": rule.citation, **dict(rule.evidence)}
    trees = [rule.applicability, rule.requirement]
    if rule.clarification_when is not None:
        trees.append(rule.clarification_when)
        if not rule.clarification:
            return False
    refs = [rule.stage_evidence, rule.continuation_evidence, *rule.action_evidence]
    for tree in trees:
        for node in tree.walk():
            if not node.evidence:
                return False
            refs.extend(node.evidence)
    if not rule.required_action.strip() or not rule.action_evidence:
        return False
    if any(ref not in evidence for ref in refs):
        return False
    for tree in trees:
        for node in tree.walk():
            if node.conditions:
                continue
            quotes = " ".join(evidence[ref].quote for ref in node.evidence)
            literals = node.value if isinstance(node.value, tuple) else (node.value,)
            if not all(literal_is_cited(literal, quotes) for literal in literals):
                return False
    return quote_names_stage(evidence[rule.stage_evidence].quote, rule.triggers_at_stage)


def _invocations(corpus: VerifiedCorpus, now: datetime) -> tuple[InvokedStage, ...]:
    for invocation in corpus.invocations:
        if (
            invocation.source_state is not SourceState.VERIFIED
            or invocation not in corpus.proved_invocations
            or not _proved(invocation.citation, corpus)
            or invocation.citation.source_doc != invocation.order_doc_id
            or invocation.citation.source_hash != invocation.order_sha256
            or not quote_names_stage(invocation.citation.quote, invocation.stage)
        ):
            raise CorpusIntegrityError("Official invocation cannot be re-proved from the snapshot")
        if invocation.invoked_at.utcoffset() is None:
            raise CorpusIntegrityError("Invocation time must include a timezone")
        if invocation.lifecycle is InvocationLifecycle.REVOKED:
            if (
                invocation.revoked_at is None
                or invocation.revoked_at.utcoffset() is None
                or invocation.revoked_at <= invocation.invoked_at
                or not _proved(invocation.revocation_citation, corpus)
            ):
                raise CorpusIntegrityError(
                    "Historical invocation requires a proved later revocation"
                )
        elif not invocation.is_current:
            raise CorpusIntegrityError("Active invocation has inconsistent revocation data")
    active = tuple(i for i in corpus.invocations if i.is_current and i.invoked_at <= now)
    if len(active) > 1:
        raise CorpusIntegrityError("Multiple current official invocations; no stage is chosen")
    return active


def _replay_stage(corpus: VerifiedCorpus, context: ReplayContext) -> InvokedStage:
    matches = tuple(
        invocation
        for invocation in corpus.invocations
        if invocation.lifecycle is InvocationLifecycle.REVOKED
        and invocation.invoked_at.date().isoformat() == context.invocation_date
        and invocation.revoked_at is not None
        and invocation.revoked_at.date().isoformat() == context.revocation_date
    )
    if len(matches) != 1:
        raise CorpusIntegrityError("Replay context must match one verified historical invocation")
    invocation = matches[0]
    at = context.at or invocation.invoked_at
    if not invocation.invoked_at <= at < invocation.revoked_at:
        raise CorpusIntegrityError("Replay instant is outside the invocation's effective interval")
    return invocation  # Keep REVOKED; never relabel history as an active invocation.


def _evaluate_rule(
    rule: Obligation, site: SiteProfile
) -> tuple[bool | None, ObligationStatus, str]:
    applies = evaluate(rule.applicability, site)
    if applies.value is None:
        return None, ObligationStatus.UNKNOWN, "Applicability is unknown. " + applies.reason
    if not applies.value:
        return (
            False,
            ObligationStatus.NOT_APPLICABLE,
            "Outside this clause's scope. " + applies.reason,
        )
    if rule.clarification_when is not None:
        unresolved = evaluate(rule.clarification_when, site)
        if unresolved.value is not False:
            return True, ObligationStatus.UNKNOWN, f"{rule.clarification} {unresolved.reason}"
    requirement = evaluate(rule.requirement, site)
    if requirement.value is None:
        return True, ObligationStatus.UNKNOWN, "Compliance is unknown. " + requirement.reason
    if requirement.value:
        return (
            True,
            ObligationStatus.MET,
            "Recorded facts satisfy this requirement. " + requirement.reason,
        )
    return (
        True,
        ObligationStatus.NOT_MET,
        "Recorded facts violate this requirement. " + requirement.reason,
    )


def resolve_obligations(
    *,
    site: ConstructionSite | SiteProfile,
    corpus: VerifiedCorpus,
    now: datetime,
    reading: StationReading | None = None,
    replay: ReplayContext | None = None,
) -> ResolutionResult:
    """Resolve using only the official invocation contained in the verified snapshot.

    No caller-supplied stage ordinal can manufacture an invocation. A discrepancy remains
    visible in stage_status while the legal applicability basis remains the official order.
    """
    if now.utcoffset() is None:
        raise ValueError("Resolution time must include a timezone")
    if isinstance(site, ConstructionSite):
        site = site.to_profile()
    active = _invocations(corpus, now)
    current = active[0] if active else None
    mode = ResolutionMode.REPLAY if replay is not None else ResolutionMode.CURRENT
    stage = _replay_stage(corpus, replay) if replay is not None else current
    replay_notice = None
    if replay is not None:
        replay_notice = (
            f"Historical scenario replay: invocation {replay.invocation_date}, "
            f"revocation {replay.revocation_date}. Uses the available verified corpus rules; "
            "their schedule revision is not established as the one in force on the replay date. "
            "This is not a current invocation or proof of historical obligations."
        )
    bands = tuple(
        b
        for b in corpus.stage_bands
        if b.source_state is SourceState.VERIFIED
        and b in corpus.proved_stage_bands
        and _proved(b.citation, corpus)
    )
    stages = stage_status(invoked=stage, reading=reading, bands=bands, mode=mode)
    results: list[ObligationResult] = []
    excluded: list[ExcludedObligation] = []
    for rule in corpus.obligations:
        if site.entity_type not in rule.entity_types:
            continue
        if not _rule_proved(rule, corpus):
            excluded.append(
                ExcludedObligation(
                    rule.obligation_id,
                    "Citation and all condition evidence are not verified "
                    "against hashed source bytes. "
                    "Excluded from resolution; run make verify.",
                )
            )
            continue
        if stage is None:
            applicable, status = False, ObligationStatus.NOT_APPLICABLE
            reason = (
                "No verified current official CAQM stage is invoked; "
                "this stage-triggered clause is not activated."
            )
        elif rule.triggers_at_stage > stage.stage:
            applicable, status = False, ObligationStatus.NOT_APPLICABLE
            reason = (
                f"Clause triggers at stage {rule.triggers_at_stage}; official stage "
                f"{stage.stage} is lower, so this clause is not activated."
            )
        else:
            applicable, status, reason = _evaluate_rule(rule, site)
        if replay_notice is not None:
            reason = replay_notice + " " + reason
        results.append(
            ObligationResult(
                obligation_id=rule.obligation_id,
                applicable=applicable,
                status=status,
                required_action=rule.required_action,
                label=rule.label,
                citation=rule.citation,
                evidence=tuple(dict.fromkeys(rule.citations)),
                reason=reason,
                issues_parchi=rule.issues_parchi,
                worker_entitlement_ref=rule.worker_entitlement_ref,
                mode=mode,
            )
        )
    return ResolutionResult(
        site_id=site.site_id,
        entity_type=site.entity_type,
        stage=stage,
        results=tuple(results),
        excluded_unsourced=tuple(excluded),
        reading=reading,
        resolved_at=now,
        stage_status=stages,
        mode=mode,
        replay_context=replay,
        replay_notice=replay_notice,
        current_stage=current,
    )
