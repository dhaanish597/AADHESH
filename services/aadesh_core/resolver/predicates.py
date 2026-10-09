"""Three-valued evaluation of the corpus's small predicate trees."""

from __future__ import annotations

from dataclasses import dataclass

from aadesh_core.domain import Predicate, SiteProfile, is_known
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.resolver.operators import apply_operator


@dataclass(frozen=True, slots=True)
class Evaluation:
    value: bool | None
    reason: str


def evaluate(predicate: Predicate, site: SiteProfile) -> Evaluation:
    if predicate.operator in ("and", "or"):
        if len(predicate.conditions) < 2:
            raise CorpusIntegrityError("Compound predicates require at least two conditions")
        children = tuple(evaluate(child, site) for child in predicate.conditions)
        # A decisive branch makes other facts unnecessary. Unknown itself never changes
        # truth value: False AND unknown is False, True OR unknown is True.
        decisive = predicate.operator == "or"
        matches = [child for child in children if child.value is decisive]
        if matches:
            return Evaluation(decisive, matches[0].reason)
        unknowns = [child.reason for child in children if child.value is None]
        if unknowns:
            return Evaluation(None, " ".join(dict.fromkeys(unknowns)))
        return Evaluation(not decisive, " ".join(child.reason for child in children))

    if predicate.field is None or predicate.conditions:
        raise CorpusIntegrityError("A comparison must name one field and have no child conditions")
    raw = site.fact(predicate.field)
    if not is_known(raw):
        return Evaluation(None, f"Required site fact {predicate.field!r} is missing or unknown.")
    try:
        holds = apply_operator(predicate.operator, raw, predicate.value)
    except TypeError:
        return Evaluation(
            None,
            f"Cannot compare site fact {predicate.field!r} ({type(raw).__name__}) "
            f"using {predicate.operator}; its value is treated as unknown.",
        )
    return Evaluation(
        holds,
        f"Site fact {predicate.field!r} {predicate.operator} {predicate.value!r} "
        f"is {'satisfied' if holds else 'not satisfied'}.",
    )
