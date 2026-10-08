"""INVARIANT: the explanation contract rejects unsupported claims.

Bedrock and Strands sit entirely outside the enforcement path. The model never decides
anything -- it rephrases what the deterministic engine already computed. The contract is what
makes that boundary real rather than aspirational, and it is checked on the model's output
before a user ever sees it.

Four things are forbidden, and each maps to a way the project could lose credibility in a
single sentence on screen:

  * citing a clause that does not exist          -> fabricated law
  * contradicting the engine's own determination -> the model overriding the resolver
  * speaking in the register of a decision       -> "approved", "guaranteed", "legal advice"
  * stating money that was never cited           -> an invented compensation figure

A violation is not an error the user sees. It falls back to deterministic text, which was
already correct.
"""

from __future__ import annotations

import pytest

from aadesh_core.domain import ObligationStatus
from aadesh_core.explanation import (
    Explanation,
    ExplanationClaim,
    ExplanationContext,
    check_explanation,
    explain_with_fallback,
)

CONTEXT = ExplanationContext(
    allowed_clause_ids=frozenset({"ob-1", "ob-2"}),
    computed_statuses={"ob-1": ObligationStatus.MET, "ob-2": ObligationStatus.UNKNOWN},
    has_cited_amount=False,
)


def an_explanation(**over) -> Explanation:
    return Explanation(
        **{
            "text": "Clause ob-1 applies to your site profile.",
            "claims": (ExplanationClaim("ob-1", ObligationStatus.MET),),
            "source": "model",
            **over,
        }
    )


def test_faithful_explanation_passes():
    assert check_explanation(an_explanation(), context=CONTEXT) == []


def test_rejects_a_clause_id_that_does_not_exist():
    violations = check_explanation(
        an_explanation(
            text="Clause ob-99 applies.",
            claims=(ExplanationClaim("ob-99", ObligationStatus.MET),),
        ),
        context=CONTEXT,
    )
    assert any(v.kind == "unknown-clause" for v in violations)


def test_rejects_a_claim_that_contradicts_the_engine():
    """ob-2 was computed UNKNOWN. The model may not upgrade it to MET."""
    violations = check_explanation(
        an_explanation(
            text="Clause ob-2 applies.",
            claims=(ExplanationClaim("ob-2", ObligationStatus.MET),),
        ),
        context=CONTEXT,
    )
    assert any(v.kind == "contradicts-engine" for v in violations)


def test_rejects_an_ungrounded_explanation():
    violations = check_explanation(an_explanation(claims=()), context=CONTEXT)
    assert any(v.kind == "ungrounded" for v in violations)


@pytest.mark.parametrize(
    "phrase",
    [
        "Your claim is approved.",
        "Payment is guaranteed.",
        "This is legal advice.",
        "You will be paid for these days.",
        "You are entitled to receive compensation.",
    ],
)
def test_rejects_decision_register_phrasing(phrase):
    violations = check_explanation(
        an_explanation(text=f"Clause ob-1 applies. {phrase}"), context=CONTEXT
    )
    assert any(v.kind == "banned-phrase" for v in violations), phrase


def test_rejects_a_rupee_figure_when_no_amount_was_cited():
    violations = check_explanation(
        an_explanation(text="Clause ob-1 applies. You may claim ₹8,000."), context=CONTEXT
    )
    assert any(v.kind == "uncited-amount" for v in violations)


def test_allows_a_rupee_figure_when_an_amount_was_cited():
    context = ExplanationContext(
        allowed_clause_ids=CONTEXT.allowed_clause_ids,
        computed_statuses=CONTEXT.computed_statuses,
        has_cited_amount=True,
    )
    violations = check_explanation(
        an_explanation(text="Clause ob-1 applies. The cited amount is ₹8,000."),
        context=context,
    )
    assert [v for v in violations if v.kind == "uncited-amount"] == []


# --- fallback behaviour ----------------------------------------------------


def _deterministic():
    return Explanation(
        text="Clause ob-1 applies to your site profile.",
        claims=(ExplanationClaim("ob-1", ObligationStatus.MET),),
        source="deterministic",
    )


def test_falls_back_to_deterministic_when_the_contract_is_violated():
    def bad_provider():
        return an_explanation(text="Your claim is approved.")

    result = explain_with_fallback(provider=bad_provider, context=CONTEXT, fallback=_deterministic)
    assert result.source == "deterministic"
    assert "approved" not in result.text


def test_falls_back_when_the_provider_raises():
    def exploding_provider():
        raise RuntimeError("Bedrock is unavailable in this region")

    result = explain_with_fallback(
        provider=exploding_provider, context=CONTEXT, fallback=_deterministic
    )
    assert result.source == "deterministic"


def test_falls_back_when_the_provider_returns_nothing():
    result = explain_with_fallback(provider=lambda: None, context=CONTEXT, fallback=_deterministic)
    assert result.source == "deterministic"


def test_a_compliant_model_explanation_is_used():
    result = explain_with_fallback(
        provider=an_explanation, context=CONTEXT, fallback=_deterministic
    )
    assert result.source == "model"


def test_deterministic_text_always_satisfies_its_own_contract():
    """The fallback must never itself be rejected, or there is nothing to fall back to."""
    assert check_explanation(_deterministic(), context=CONTEXT) == []
