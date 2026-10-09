"""The comparison operators used by the corpus, without coercion of unknown or bad types."""

from __future__ import annotations

from math import isfinite
from typing import Any

from aadesh_core.errors import CorpusIntegrityError

OPERATORS = frozenset({"eq", "gte", "in", "not_in"})


def _same_type(fact: Any, expected: Any) -> bool:
    if type(expected) in (int, float):
        return type(fact) in (int, float) and isfinite(fact) and isfinite(expected)
    return type(fact) is type(expected) and isinstance(expected, str | bool)


def apply_operator(operator: str, fact: Any, expected: Any) -> bool:
    if operator not in OPERATORS:
        raise CorpusIntegrityError(f"Unknown operator {operator!r}")
    if operator in ("in", "not_in"):
        if not isinstance(expected, tuple | list) or not expected:
            raise TypeError("Membership requires a non-empty list of known values")
        if not all(_same_type(fact, item) for item in expected):
            raise TypeError("Membership operands must have matching scalar types")
        present = fact in expected
        return present if operator == "in" else not present
    if not _same_type(fact, expected):
        raise TypeError("Comparison operands must have matching scalar types")
    if operator == "gte":
        if type(expected) not in (int, float):
            raise TypeError("gte requires finite numbers")
        return fact >= expected
    return fact == expected
