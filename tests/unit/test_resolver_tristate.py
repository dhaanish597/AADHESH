"""INVARIANT: a missing fact resolves to UNKNOWN, never to NOT_MET.

This is the most important behaviour in the resolver. A compliance tool that treats
"I don't know" as "no" produces confident false negatives -- it would tell a supervisor an
obligation does not apply when the truth is that nobody recorded the fact it keys on. For a
displaced worker that is the difference between a documented entitlement and silence.

`unknown` must therefore be a first-class outcome everywhere, and never collapse into a
boolean.
"""

from __future__ import annotations

import pytest

from aadesh_core.domain import UNKNOWN_FACT, ObligationStatus
from aadesh_core.resolver import resolve_obligations
from tests.support.builders import FIXED_NOW, invoked_stage, obligation, reading, site, snapshot

ALL_OPERATORS = ["eq", "gte", "in", "not_in"]


def _resolve(**over):
    kwargs = {
        "site": site(),
        "stage": invoked_stage(),
        "obligations": [obligation()],
        "reading": reading(),
        "now": FIXED_NOW,
        **over,
    }
    kwargs["corpus"] = snapshot(stage=kwargs.pop("stage"), obligations=kwargs.pop("obligations"))
    return resolve_obligations(**kwargs)


def test_fact_absent_from_profile_yields_unknown():
    result_set = _resolve(site=site(facts={}))
    (result,) = result_set.results
    assert result.status is ObligationStatus.UNKNOWN
    assert "has_dust_generating_activity" in result.reason


def test_fact_explicitly_unknown_yields_unknown():
    result_set = _resolve(site=site(facts={"has_dust_generating_activity": UNKNOWN_FACT}))
    (result,) = result_set.results
    assert result.status is ObligationStatus.UNKNOWN


def test_satisfied_condition_yields_met():
    result_set = _resolve(site=site(facts={"has_dust_generating_activity": True}))
    (result,) = result_set.results
    assert result.status is ObligationStatus.MET


def test_unsatisfied_condition_yields_not_met():
    result_set = _resolve(site=site(facts={"has_dust_generating_activity": False}))
    (result,) = result_set.results
    assert result.status is ObligationStatus.NOT_MET


@pytest.mark.parametrize("operator", ALL_OPERATORS)
def test_missing_fact_never_yields_not_met_for_any_operator(operator):
    """The headline invariant, swept across every operator the corpus schema permits."""
    value = ["a", "b"] if operator in ("in", "not_in") else 1
    result_set = _resolve(
        site=site(facts={}),
        obligations=[obligation(operator=operator, value=value)],
    )
    (result,) = result_set.results
    assert result.status is not ObligationStatus.NOT_MET, (
        f"operator {operator!r} inferred NOT_MET from a missing fact"
    )
    assert result.status is ObligationStatus.UNKNOWN


@pytest.mark.parametrize("operator", ALL_OPERATORS)
def test_explicitly_unknown_fact_never_yields_not_met_for_any_operator(operator):
    value = ["a", "b"] if operator in ("in", "not_in") else 1
    result_set = _resolve(
        site=site(facts={"has_dust_generating_activity": UNKNOWN_FACT}),
        obligations=[obligation(operator=operator, value=value)],
    )
    (result,) = result_set.results
    assert result.status is ObligationStatus.UNKNOWN


def test_no_invoked_stage_cannot_activate_a_requirement():
    """Verified absence never becomes a legal activation or a compliance violation."""
    result_set = _resolve(stage=None)
    (result,) = result_set.results
    assert result.status is ObligationStatus.NOT_APPLICABLE
    assert result.applicable is False
    assert "no verified current" in result.reason.lower()


def test_obligation_triggering_above_invoked_stage_is_not_applicable():
    """This one IS safely knowable: stage 4 obligations do not apply when 3 is invoked."""
    result_set = _resolve(
        stage=invoked_stage(stage=3),
        obligations=[obligation(triggers_at_stage=4)],
    )
    (result,) = result_set.results
    assert result.status is ObligationStatus.NOT_APPLICABLE
    assert result.applicable is False
    assert "stage 4" in result.reason


def test_obligation_triggering_at_or_below_invoked_stage_is_evaluated():
    result_set = _resolve(
        stage=invoked_stage(stage=4),
        obligations=[obligation(triggers_at_stage=3)],
    )
    (result,) = result_set.results
    assert result.status is ObligationStatus.MET


def test_incomparable_types_yield_unknown_rather_than_crashing():
    """A corpus authoring slip must degrade to UNKNOWN, not take the resolver down."""
    result_set = _resolve(
        site=site(facts={"has_dust_generating_activity": "yes"}),
        obligations=[obligation(operator="gte", value=10)],
    )
    (result,) = result_set.results
    assert result.status is ObligationStatus.UNKNOWN
    assert "compare" in result.reason.lower()


def test_unknown_results_are_separately_addressable():
    result_set = _resolve(
        obligations=[
            obligation(obligation_id="ob-known"),
            obligation(obligation_id="ob-unknown", field="absent_fact"),
        ]
    )
    assert [r.obligation_id for r in result_set.unknown] == ["ob-unknown"]
    assert [r.obligation_id for r in result_set.applicable] == ["ob-known", "ob-unknown"]
    assert result_set.unknown[0].applicable is True  # Missing compliance, known applicability.


def test_resolution_is_deterministic():
    """Same inputs, same outputs. No clock reads, no network, no dict ordering surprises."""
    kwargs = {
        "site": site(facts={"has_dust_generating_activity": True, "other": UNKNOWN_FACT}),
        "stage": invoked_stage(),
        "obligations": [
            obligation(obligation_id="ob-1"),
            obligation(obligation_id="ob-2", field="other"),
            obligation(obligation_id="ob-3", field="missing"),
        ],
        "reading": reading(),
        "now": FIXED_NOW,
    }
    kwargs["corpus"] = snapshot(stage=kwargs.pop("stage"), obligations=kwargs.pop("obligations"))
    first = resolve_obligations(**kwargs)
    second = resolve_obligations(**kwargs)
    assert first == second
