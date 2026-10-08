"""Builders for explanation-layer tests.

These assemble REAL `ResolutionResult`s from the deterministic resolver, using the same test
doubles the resolution tests use, so an explanation test exercises the actual fact shapes the
production path produces. Fake model responses are built from the request, which is what lets
`faithful_response` be faithful and the hallucination builders differ from it by exactly one
field.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aadesh_core.domain import (
    InvocationLifecycle,
    ResolutionResult,
    SourceState,
    StageBand,
)
from aadesh_core.explanation import ExplanationRequest, ExplanationResponse
from aadesh_core.resolver import resolve_obligations
from tests.support.builders import FIXED_NOW, citation, invoked_stage, obligation, site, snapshot
from tests.support.resolution import with_test_stage

REPLAY_INVOCATION_DATE = "2026-01-16"
REPLAY_REVOCATION_DATE = "2026-01-22"


def verified_band(
    *, stage: int = 3, lower: float = 401.0, upper: float | None = None, pollutant: str = "aqi"
) -> StageBand:
    return StageBand(
        stage=stage,
        pollutant=pollutant,
        aqi_lower=lower,
        aqi_upper=upper,
        citation=citation(quote=f"Test band implies Stage {stage}."),
        source_state=SourceState.VERIFIED,
    )


def resolved_result(
    *,
    stage: int = 3,
    facts: dict[str, Any] | None = None,
    reading_value: float | None = None,
    bands: tuple[StageBand, ...] = (),
) -> ResolutionResult:
    """A real resolution: one verified obligation at `stage`, over a construction site."""
    corpus = with_test_stage(snapshot(obligations=[obligation()], bands=bands), stage)
    if reading_value is not None:
        from tests.support.builders import reading as reading_builder

        resolved_reading = reading_builder(value=reading_value)
    else:
        resolved_reading = None
    return resolve_obligations(
        site=site(facts=facts) if facts is not None else site(),
        corpus=corpus,
        now=FIXED_NOW,
        reading=resolved_reading,
    )


def revoked_invocation_corpus() -> tuple[Any, Any]:
    """A snapshot with one REVOKED Stage III invocation, plus its replay context."""
    from aadesh_core.domain import ReplayContext

    revocation = citation(quote="Test authority revokes Stage III.", source_doc="test-order")
    invocation = invoked_stage(
        stage=3,
        invoked_at=datetime(2026, 1, 16, 9, 0, tzinfo=UTC),
        lifecycle=InvocationLifecycle.REVOKED,
        revoked_at=datetime(2026, 1, 22, 9, 0, tzinfo=UTC),
        revocation_citation=revocation,
        citation=citation(quote="Test authority invokes Stage III.", source_doc="test-order"),
    )
    corpus = snapshot(obligations=[obligation()], stage=invocation)
    replay = ReplayContext(
        invocation_date=REPLAY_INVOCATION_DATE, revocation_date=REPLAY_REVOCATION_DATE
    )
    return corpus, replay


def replay_result() -> ResolutionResult:
    corpus, replay = revoked_invocation_corpus()
    return resolve_obligations(site=site(), corpus=corpus, now=FIXED_NOW, replay=replay)


def response_payload(request: ExplanationRequest, **over: Any) -> dict[str, Any]:
    """A faithful response payload, with selected fields overridden."""
    payload: dict[str, Any] = {
        "summary": "This site has a GRAP obligation under the official invocation.",
        "why_this_action": request.stage_reason,
        "official_stage": request.official_stage,
        "implied_stage": request.implied_stage,
        "replay_status": request.mode,
        "claims": [{"clause_id": o.obligation_id, "status": o.status} for o in request.obligations],
        "source_references": [
            {
                "source_doc": c.source_doc,
                "page": c.page,
                "quote": c.quote,
                "source_hash": c.source_hash,
            }
            for c in request.citations
        ],
        "uncertainties": [],
        "disclaimer": "This restates a deterministic decision and is not legal advice.",
    }
    payload.update(over)
    return payload


def faithful_response(request: ExplanationRequest, **over: Any) -> ExplanationResponse:
    return ExplanationResponse.from_payload(
        response_payload(request, **over), model_metadata={"provider": "fake"}
    )


def response_from(request: ExplanationRequest, **over: Any) -> ExplanationResponse:
    """Alias kept explicit for readability in hallucination tests."""
    return ExplanationResponse.from_payload(
        response_payload(request, **over), model_metadata={"provider": "fake"}
    )


__all__ = [
    "REPLAY_INVOCATION_DATE",
    "REPLAY_REVOCATION_DATE",
    "faithful_response",
    "replay_result",
    "resolved_result",
    "response_from",
    "response_payload",
    "revoked_invocation_corpus",
    "verified_band",
]
