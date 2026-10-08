"""Comparison operators available to the rules corpus.

Deliberately a small, closed set. A corpus is data, and data that can express arbitrary
computation is a program -- at which point "rules as data" stops being true and the
testability and traceability that justify it are gone.

Every operator here is total with respect to *presence*: the resolver guarantees a fact
exists and is known before any of these is called. They are not total with respect to
*type*, and the resolver converts a TypeError into UNKNOWN rather than crashing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aadesh_core.errors import CorpusIntegrityError

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda fact, expected: bool(fact == expected),
    "neq": lambda fact, expected: bool(fact != expected),
    "gt": lambda fact, expected: bool(fact > expected),
    "gte": lambda fact, expected: bool(fact >= expected),
    "lt": lambda fact, expected: bool(fact < expected),
    "lte": lambda fact, expected: bool(fact <= expected),
    "in": lambda fact, expected: bool(fact in expected),
    "not_in": lambda fact, expected: bool(fact not in expected),
}


def apply_operator(operator: str, fact: Any, expected: Any) -> bool:
    """Apply `operator`, raising CorpusIntegrityError for an unknown one.

    An unrecognised operator is an authoring bug in the corpus, not a runtime condition to
    degrade around. Guessing what was meant is the opposite of what Aadesh is for.
    """
    try:
        fn = OPERATORS[operator]
    except KeyError:
        raise CorpusIntegrityError(
            f"Unknown operator {operator!r}. Permitted operators: "
            f"{', '.join(sorted(OPERATORS))}. Fix the corpus entry."
        ) from None
    return fn(fact, expected)
