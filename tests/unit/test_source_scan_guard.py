"""Meta-tests for the legal-data guard scanner.

A guard that has never failed proves nothing. These tests feed the scanner source
strings that are deliberately in breach, and assert it catches them. That is what
licenses the companion test (test_no_hardcoded_legal_data.py) to assert the real
tree is clean -- without this file, a scanner that always returned [] would look
like a passing invariant.

Same philosophy as `make verify-tamper`.
"""

from __future__ import annotations

from tests.support.source_scan import scan_source

CLEAN = '''
"""A module with no legal facts in it."""
from dataclasses import dataclass

STALENESS_SECONDS = 5400
MAX_ROSTER = 40


@dataclass(frozen=True)
class Reading:
    value: float
    station_id: str
'''


def test_flags_an_aqi_band_threshold():
    bad = "SEVERE_PLUS_LOWER_BOUND = 401\n"
    violations = scan_source(bad, path="domain/stages.py")
    assert violations, "scanner failed to flag a hardcoded AQI band threshold"
    assert any(v.kind == "numeric-literal" for v in violations)
    assert any("401" in v.detail for v in violations)


def test_flags_a_threshold_buried_in_a_comparison():
    bad = "def implied_stage(aqi):\n    if aqi > 400:\n        return 4\n    return None\n"
    violations = scan_source(bad, path="resolver/stage.py")
    assert any(v.kind == "numeric-literal" for v in violations), (
        "scanner must catch a threshold used inline in a comparison, "
        "not only one bound to a constant"
    )


def test_flags_a_rupee_constant():
    bad = "DISPLACEMENT_AMOUNT_INR = 8000\n"
    violations = scan_source(bad, path="domain/money.py")
    kinds = {v.kind for v in violations}
    assert "money-constant" in kinds, f"expected money-constant violation, got {kinds}"


def test_flags_a_currency_symbol():
    bad = 'LABEL = "₹1,02,000 documented"\n'
    violations = scan_source(bad, path="domain/labels.py")
    assert any(v.kind == "currency-symbol" for v in violations)


def test_flags_money_constant_even_when_value_is_small():
    """A small number dodges the numeric window, so the name-based rule must still fire."""
    bad = "PER_DAY_WAGE = 20\n"
    violations = scan_source(bad, path="domain/money.py")
    assert any(v.kind == "money-constant" for v in violations)


def test_clean_source_produces_no_violations():
    assert scan_source(CLEAN, path="domain/readings.py") == []


def test_suppression_comment_is_honoured():
    """An explicit, reviewable opt-out. Needed so the guard stays usable."""
    suppressed = "HTTP_UNPROCESSABLE = 422  # noqa: aadesh-no-legal-literal\n"
    assert scan_source(suppressed, path="domain/http.py") == []


def test_suppression_does_not_leak_to_other_lines():
    source = (
        "OK = 422  # noqa: aadesh-no-legal-literal\n"
        "SEVERE_LOWER = 401\n"
    )
    violations = scan_source(source, path="domain/http.py")
    assert len(violations) == 1
    assert violations[0].line == 2
