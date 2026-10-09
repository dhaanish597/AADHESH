"""The explicit-unknown sentinel for site facts.

A site profile distinguishes three cases, and conflating any two of them produces a
confident false answer:

  * the fact is recorded and true
  * the fact is recorded and false
  * **the fact is not known** -- either absent from the profile, or present and explicitly
    marked unknown because someone looked and could not establish it

`UNKNOWN_FACT` represents the third case when it needs to be stated rather than merely
omitted ("we asked, nobody knew" is worth recording differently from "nobody asked").
"""

from __future__ import annotations

from typing import Any, Final


class _UnknownFact:
    """Singleton marking a site fact whose value is not known."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNKNOWN_FACT"

    def __bool__(self) -> bool:
        # Refusing a truth value is the whole point. If this sentinel were falsy, every
        # `if site.facts.get(field):` in the codebase would quietly read "unknown" as "no".
        raise TypeError(
            "UNKNOWN_FACT has no truth value. Handle the unknown case explicitly: "
            "`if value is UNKNOWN_FACT: ...`"
        )

    def __reduce__(self) -> str:
        return "UNKNOWN_FACT"


UNKNOWN_FACT: Final[Any] = _UnknownFact()


class _MissingFact:
    """Singleton for an absent key, distinct from an explicitly unknown fact."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING_FACT"

    def __bool__(self) -> bool:
        raise TypeError("MISSING_FACT has no truth value. Handle missing facts explicitly.")

    def __reduce__(self) -> str:
        return "MISSING_FACT"


MISSING_FACT: Final[Any] = _MissingFact()
"""Returned by SiteProfile.fact() when the key is absent entirely."""


def is_known(value: Any) -> bool:
    """Whether a value is recorded; comparison validity is checked separately."""
    return value is not UNKNOWN_FACT and value is not MISSING_FACT and value is not None
