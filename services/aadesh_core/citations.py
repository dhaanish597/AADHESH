"""Shared typography, citation traversal and stage-name checks; no legal decisions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from aadesh_core.domain.models import stage_name

CITATION_KEYS = {"source_doc", "page", "quote"}


def page_text_sha256(text: str) -> str:
    """Bind extracted evidence too, independent of Git/platform newline conversion."""
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text)
    folded = folded.replace("’", "'").replace("‘", "'")  # noqa: RUF001
    folded = folded.replace("“", '"').replace("”", '"')
    folded = folded.replace("–", "-").replace("—", "-")  # noqa: RUF001
    return " ".join(folded.split()).casefold()


def quote_names_stage(quote: str, stage: int) -> bool:
    """Match a whole ordinal: 'Stage III' must never prove Stage I or Stage II."""
    roman = stage_name(stage).removeprefix("Stage ").casefold()
    return any(
        re.search(r"\bstage[\s-]+" + re.escape(ordinal) + r"\b", normalise(quote))
        for ordinal in (str(stage), roman)
    )


def literal_is_cited(literal: Any, quotes: str) -> bool:
    """Booleans express polarity; every textual or numeric legal literal must be quoted."""
    if isinstance(literal, bool):
        return True
    if isinstance(literal, str):
        return bool(literal.strip()) and normalise(literal) in normalise(quotes)
    if type(literal) in (int, float):
        return bool(
            re.search(r"(?<![\d.])" + re.escape(format(literal, "g")) + r"(?![\d.])", quotes)
        )
    return False


def labelled_citations(value: Any, path: str = "citation") -> list[tuple[str, dict]]:
    """Every nested citation, including predicate evidence, amounts and revocations."""
    found: list[tuple[str, dict]] = []
    if isinstance(value, dict):
        if value.keys() >= CITATION_KEYS:
            found.append((path, value))
        for name, child in value.items():
            found.extend(labelled_citations(child, f"{path}.{name}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(labelled_citations(child, f"{path}[{index}]"))
    return found
