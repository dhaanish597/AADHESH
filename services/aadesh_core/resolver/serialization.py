"""Stable JSON-ready output for local testing and subsequent deterministic consumers."""

from __future__ import annotations

from typing import Any

from aadesh_core.domain import Citation, InvokedStage, ObligationStatus, ResolutionResult


def _citation(citation: Citation | None) -> dict[str, Any] | None:
    if citation is None:
        return None
    return {
        "source_doc": citation.source_doc,
        "source_page": citation.page,
        "source_quote": citation.quote,
        "source_hash": citation.source_hash,
    }


def _invocation(invocation: InvokedStage | None) -> dict[str, Any] | None:
    if invocation is None:
        return None
    return {
        "stage": invocation.stage,
        "invoked_at": invocation.invoked_at.isoformat(),
        "lifecycle": invocation.lifecycle.value,
        "citation": _citation(invocation.citation),
        "revoked_at": invocation.revoked_at.isoformat() if invocation.revoked_at else None,
        "revocation_citation": _citation(invocation.revocation_citation),
    }


def resolution_to_dict(result: ResolutionResult) -> dict[str, Any]:
    replay = result.replay_context
    reading = result.reading
    return {
        "site_id": result.site_id,
        "entity_type": result.entity_type,
        "mode": result.mode.value,
        "resolved_at": result.resolved_at.isoformat(),
        "official_stage": (
            result.stage_status.official_stage
            if result.stage_status.official_stage is not None
            else "NONE"
        ),
        "current_official_stage": result.current_stage.stage if result.current_stage else "NONE",
        "implied_stage": result.stage_status.implied_stage,
        "stage_status": result.stage_status.status.value,
        "stage_reason": result.stage_status.reason,
        "official_invocation": _invocation(result.stage),
        "implied_stage_citation": _citation(result.stage_status.implied.citation)
        if result.stage_status.implied
        else None,
        "replay_context": {
            "invocation_date": replay.invocation_date,
            "revocation_date": replay.revocation_date,
            "at": replay.at.isoformat() if replay.at else None,
        }
        if replay
        else None,
        "replay_notice": result.replay_notice,
        "reading": {
            "station_id": reading.station_id,
            "parameter": reading.parameter,
            "value": reading.value,
            "observed_at": reading.observed_at.isoformat(),
            "ingested_at": reading.ingested_at.isoformat(),
            "provenance": reading.provenance.value,
        }
        if reading
        else None,
        "summary": {
            "applicable": len(result.applicable),
            **{
                status.name: sum(r.status is status for r in result.results)
                for status in ObligationStatus
            },
        },
        "fully_sourced": result.fully_sourced,
        "obligations": [
            {
                "obligation_id": obligation.obligation_id,
                "mode": obligation.mode.value,
                "applicable": obligation.applicable,
                "status": obligation.status.name,
                "required_action": obligation.required_action,
                "reason": obligation.reason,
                **_citation(obligation.citation),
                "evidence": [_citation(citation) for citation in obligation.evidence],
            }
            for obligation in result.results
        ],
        "excluded_obligations": [
            {
                "obligation_id": excluded.obligation_id,
                "reason": excluded.reason,
                "mode": result.mode.value,
            }
            for excluded in result.excluded_unsourced
        ],
    }
