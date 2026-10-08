"""The output contract that keeps the model outside the enforcement path.

Aadesh's architecture claim is that no model determines a legal obligation. That claim is
only as good as what happens to the model's output before a user reads it. This module is
that step: a deterministic check over generated prose, with a deterministic sentence ready
for when it fails.

The model is given two jobs and no others: render an already-computed result into plain
language, and answer a question by citing already-computed results. Everything the contract
forbids is a way of exceeding that brief.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from aadesh_core.domain import ObligationStatus

#: Phrasing that speaks in the register of a decision Aadesh is not entitled to make.
#: Aadesh says "this clause applies to your profile", never "you are permitted" or
#: "you will be paid".
BANNED_PHRASES: tuple[str, ...] = (
    "approved",
    "guaranteed",
    "legal advice",
    "you will be paid",
    "you will receive",
    "entitled to receive",
    "we have filed",
    "your claim has been",
)

#: Any mention of money. Permitted only when a cited amount exists in the corpus.
#: The symbols below are a DETECTOR, not a figure -- this is the one place in the core where
#: a currency symbol legitimately appears, hence the explicit opt-out from the guard.
_MONEY_RE = re.compile(r"[₹₨]|\bRs\.|\bINR\b", re.IGNORECASE)  # noqa: aadesh-no-legal-literal


@dataclass(frozen=True, slots=True)
class ExplanationClaim:
    """An assertion the explanation makes about one clause."""

    clause_id: str
    status: ObligationStatus


@dataclass(frozen=True, slots=True)
class Explanation:
    """Generated prose, plus the structured claims it is making.

    Requiring claims alongside the text is what makes the contract checkable. Prose alone
    would have to be parsed to know what it asserted, and a parser is just another thing to
    be wrong.
    """

    text: str
    claims: tuple[ExplanationClaim, ...]
    source: str  # "deterministic" | "model"


@dataclass(frozen=True, slots=True)
class ExplanationContext:
    """What the deterministic engine already computed. The model may only restate this."""

    allowed_clause_ids: frozenset[str]
    computed_statuses: Mapping[str, ObligationStatus]
    has_cited_amount: bool = False


@dataclass(frozen=True, slots=True)
class ContractViolation:
    kind: str
    detail: str


def check_explanation(
    explanation: Explanation, *, context: ExplanationContext
) -> list[ContractViolation]:
    """Return every way `explanation` breaches its contract. Empty list means it may be shown."""
    violations: list[ContractViolation] = []

    if not explanation.claims:
        violations.append(
            ContractViolation(
                kind="ungrounded",
                detail=(
                    "Explanation cites no clause. Every statement Aadesh shows must be "
                    "traceable to a computed result."
                ),
            )
        )

    for claim in explanation.claims:
        if claim.clause_id not in context.allowed_clause_ids:
            violations.append(
                ContractViolation(
                    kind="unknown-clause",
                    detail=(
                        f"Cites clause {claim.clause_id!r}, which the engine did not "
                        f"compute. Known clauses: {sorted(context.allowed_clause_ids)}."
                    ),
                )
            )
            continue

        computed = context.computed_statuses.get(claim.clause_id)
        if computed is not None and claim.status is not computed:
            violations.append(
                ContractViolation(
                    kind="contradicts-engine",
                    detail=(
                        f"States clause {claim.clause_id!r} is {claim.status.value!r}, but "
                        f"the resolver computed {computed.value!r}. The model does not get "
                        f"to overrule the resolver."
                    ),
                )
            )

    lowered = explanation.text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            violations.append(
                ContractViolation(
                    kind="banned-phrase",
                    detail=(
                        f"Contains {phrase!r}. Aadesh is not a government application and "
                        f"not legal advice; it cannot speak as though a decision was made."
                    ),
                )
            )

    if not context.has_cited_amount and _MONEY_RE.search(explanation.text):
        violations.append(
            ContractViolation(
                kind="uncited-amount",
                detail=(
                    "States a monetary figure, but no entitlement in the corpus carries a "
                    "cited amount. Report displaced worker-days instead."
                ),
            )
        )

    return violations


def explain_with_fallback(
    *,
    provider: Callable[[], Explanation | None],
    context: ExplanationContext,
    fallback: Callable[[], Explanation],
    on_violation: Callable[[list[ContractViolation]], None] | None = None,
) -> Explanation:
    """Run `provider`, and use `fallback` if it fails, returns nothing, or breaches contract.

    Fails closed in every direction. The deterministic text was already correct, so falling
    back costs polish and nothing else -- which is exactly why the model is allowed to be
    unavailable.
    """
    try:
        candidate = provider()
    except Exception as exc:
        if on_violation:
            on_violation([ContractViolation(kind="provider-error", detail=str(exc))])
        return fallback()

    if candidate is None:
        if on_violation:
            on_violation([ContractViolation(kind="provider-empty", detail="No output.")])
        return fallback()

    violations = check_explanation(candidate, context=context)
    if violations:
        if on_violation:
            on_violation(violations)
        return fallback()

    return candidate
