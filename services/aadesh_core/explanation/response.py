"""The structured output the model must produce, and the strict parser for it.

Preferring a structured response over free prose is what makes the boundary checkable. A
paragraph would have to be parsed to learn what it asserted; here the model states its claims,
its echoed stage/replay status and its citations as data, and the deterministic checks in
`grounding.py` can refuse a response that contradicts the engine.

Parsing is deliberately strict. A response that is missing a field, has the wrong type, or
names a status outside the closed vocabulary raises `ValueError`, and the caller falls back to
the deterministic text. Lenient parsing would let a malformed answer through the contract by
accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from aadesh_core.domain import ObligationStatus
from aadesh_core.explanation.context import DEFAULT_DISCLAIMER, SCHEMA_VERSION
from aadesh_core.explanation.contract import ExplanationClaim


@dataclass(frozen=True, slots=True)
class SourceReference:
    """A citation the model says supports its explanation. Grounded against the request."""

    source_doc: str
    page: int
    quote: str | None = None
    source_hash: str | None = None


@dataclass(frozen=True, slots=True)
class ExplanationResponse:
    """A model's rendering of an already-computed result. NEVER authoritative, never stored as
    the decision -- the deterministic result lives separately in the caller."""

    summary: str
    why_this_action: str
    official_stage: str
    implied_stage: str
    replay_status: str
    claims: tuple[ExplanationClaim, ...] = ()
    source_references: tuple[SourceReference, ...] = ()
    uncertainties: tuple[str, ...] = ()
    disclaimer: str = DEFAULT_DISCLAIMER
    model_metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @property
    def text(self) -> str:
        """Summary and reason, joined. This is what the contract checks for register."""
        return " ".join(part for part in (self.summary, self.why_this_action) if part).strip()

    @classmethod
    def from_payload(
        cls, payload: object, *, model_metadata: Mapping[str, str] | None = None
    ) -> ExplanationResponse:
        if not isinstance(payload, Mapping):
            raise ValueError("Explanation response must be a JSON object")
        summary = _require_str(payload, "summary")
        why = _optional_str(payload, "why_this_action")
        official = _require_str(payload, "official_stage")
        implied = _require_str(payload, "implied_stage")
        replay = _require_str(payload, "replay_status")
        claims = tuple(_claim(item) for item in _require_list(payload, "claims"))
        references = tuple(
            _reference(item) for item in _optional_list(payload, "source_references")
        )
        uncertainties = tuple(
            _non_empty_str(item, "uncertainties[]")
            for item in _optional_list(payload, "uncertainties")
        )
        disclaimer = _optional_str(payload, "disclaimer") or DEFAULT_DISCLAIMER
        return cls(
            summary=summary,
            why_this_action=why,
            official_stage=official,
            implied_stage=implied,
            replay_status=replay,
            claims=claims,
            source_references=references,
            uncertainties=uncertainties,
            disclaimer=disclaimer,
            model_metadata=MappingProxyType(dict(model_metadata or {})),
        )


def _require_str(payload: Mapping, key: str) -> str:
    if key not in payload:
        raise ValueError(f"Explanation response is missing required field {key!r}")
    return _non_empty_str(payload[key], key)


def _optional_str(payload: Mapping, key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return _non_empty_str(value, key)


def _non_empty_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string, got {type(value).__name__}")
    return value.strip()


def _require_list(payload: Mapping, key: str) -> list:
    if key not in payload:
        raise ValueError(f"Explanation response is missing required field {key!r}")
    return _as_list(payload[key], key)


def _optional_list(payload: Mapping, key: str) -> list:
    value = payload.get(key)
    if value is None:
        return []
    return _as_list(value, key)


def _as_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list, got {type(value).__name__}")
    return value


def _claim(item: object) -> ExplanationClaim:
    if not isinstance(item, Mapping):
        raise ValueError("Each claim must be an object with clause_id and status")
    clause_id = _non_empty_str(item.get("clause_id"), "claim.clause_id")
    raw_status = item.get("status")
    try:
        status = ObligationStatus(raw_status)
    except ValueError as exc:
        raise ValueError(f"claim.status {raw_status!r} is not a known obligation status") from exc
    if not clause_id:
        raise ValueError("claim.clause_id must be non-empty")
    return ExplanationClaim(clause_id=clause_id, status=status)


def _reference(item: object) -> SourceReference:
    if not isinstance(item, Mapping):
        raise ValueError("Each source reference must be an object")
    source_doc = _non_empty_str(item.get("source_doc"), "source_references[].source_doc")
    page = item.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
        raise ValueError(f"source_references[].page must be a positive integer, got {page!r}")
    quote = item.get("quote")
    if quote is not None and not isinstance(quote, str):
        raise ValueError("source_references[].quote must be a string when present")
    source_hash = item.get("source_hash")
    if source_hash is not None and not isinstance(source_hash, str):
        raise ValueError("source_references[].source_hash must be a string when present")
    return SourceReference(
        source_doc=source_doc, page=page, quote=quote, source_hash=source_hash or None
    )


__all__ = ["ExplanationResponse", "SourceReference"]
