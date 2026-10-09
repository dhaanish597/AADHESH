"""Unknown propagation and type safety for the operators the real corpus needs."""

from __future__ import annotations

from itertools import product

import pytest

from aadesh_core.domain import MISSING_FACT, UNKNOWN_FACT, Predicate, SiteProfile, is_known
from aadesh_core.resolver.predicates import evaluate


def leaf(field):
    return Predicate("eq", ("clause",), field=field, value=True)


@pytest.mark.parametrize(
    "operator,left,right",
    [
        (operator, left, right)
        for operator in ("and", "or")
        for left, right in product((True, False, None), repeat=2)
    ],
)
def test_three_valued_logic_never_assigns_a_truth_value_to_unknown(operator, left, right):
    site = SiteProfile("site", "construction_site", "", {"left": left, "right": right})
    tree = Predicate(operator, ("clause",), conditions=(leaf("left"), leaf("right")))
    actual = evaluate(tree, site).value
    if operator == "and":
        expected = (
            False if left is False or right is False else (None if None in (left, right) else True)
        )
    else:
        expected = (
            True if left is True or right is True else (None if None in (left, right) else False)
        )
    assert actual is expected


@pytest.mark.parametrize("unknown", [None, UNKNOWN_FACT, MISSING_FACT])
@pytest.mark.parametrize(
    "operator,value", [("eq", False), ("gte", 500), ("in", ("x",)), ("not_in", ("x",))]
)
def test_null_and_explicit_unknown_are_not_comparable_facts(unknown, operator, value):
    site = SiteProfile("site", "construction_site", "", {"fact": unknown})
    result = evaluate(Predicate(operator, ("clause",), field="fact", value=value), site)
    assert result.value is None


@pytest.mark.parametrize(
    "operator,raw,expected",
    [
        ("eq", 1, True),
        ("eq", 0, False),
        ("eq", "false", False),
        ("gte", True, 500),
        ("gte", "750", 500),
        ("gte", float("nan"), 500),
        ("in", 1, (True, False)),
        ("not_in", None, ("a", "b")),
        ("eq", [], False),
        ("gte", float("inf"), 500),
    ],
)
def test_invalid_types_cannot_turn_into_known_compliance(operator, raw, expected):
    site = SiteProfile("site", "construction_site", "", {"fact": raw})
    result = evaluate(Predicate(operator, ("clause",), field="fact", value=expected), site)
    assert result.value is None


def test_site_profile_copies_its_inputs_for_deterministic_resolution():
    facts = {"fact": None}
    site = SiteProfile("site", "construction_site", "", facts)
    facts["fact"] = True
    assert evaluate(leaf("fact"), site).value is None
    with pytest.raises(TypeError):
        site.facts["fact"] = True


def test_recorded_false_is_known_but_all_forms_of_absence_are_unknown():
    profile = SiteProfile("site", "construction_site", "", {"flag": False})
    assert is_known(profile.fact("flag"))
    assert is_known(0)
    assert not is_known(profile.fact("absent"))
    assert not is_known(None)
    assert not is_known(UNKNOWN_FACT)


@pytest.mark.parametrize("sentinel", [MISSING_FACT, UNKNOWN_FACT])
def test_absent_and_unknown_facts_refuse_boolean_coercion(sentinel):
    with pytest.raises(TypeError, match="no truth value"):
        bool(sentinel)
