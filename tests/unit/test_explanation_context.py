"""INVARIANT: the explanation input is explicit, structured, and free of personal data.

The model is given a `ExplanationRequest` and nothing else. These tests pin its shape: the
deterministic stage and replay facts are present so the model can echo them, citations are
present so it can cite them, and no worker personal data is present at all.
"""

from __future__ import annotations

import json

from aadesh_core.domain import ObligationStatus
from aadesh_core.explanation import (
    ExplanationKind,
    request_for_parchi,
    request_for_resolution,
)
from tests.support.authz_builders import parchi_domain
from tests.support.explanation_builders import (
    replay_result,
    resolved_result,
    verified_band,
)


def test_request_carries_stage_and_replay_echo_fields():
    request = request_for_resolution(resolved_result(stage=3), kind=ExplanationKind.STAGE)
    assert request.kind is ExplanationKind.STAGE
    assert request.mode == "CURRENT"
    payload = request.to_prompt_payload()
    assert payload["official_stage"] == "Stage III"
    assert payload["replay_status"] == "CURRENT"
    assert payload["schema_version"] == "explanation/1"


def test_contract_context_maps_obligations_to_statuses():
    result = resolved_result(stage=3)
    request = request_for_resolution(result)
    context = request.contract_context()
    assert context.allowed_clause_ids == frozenset(r.obligation_id for r in result.results)
    assert context.computed_statuses["test-ob-01"] is ObligationStatus.MET


def test_payload_is_json_serialisable_and_lists_citations():
    result = resolved_result(stage=3)
    request = request_for_resolution(result)
    payload = request.to_prompt_payload()
    encoded = json.dumps(payload, ensure_ascii=True)
    assert "citations" in payload
    assert payload["citations"]
    assert "source_hash" in encoded


def test_aqi_discrepancy_request_exposes_both_stages():
    result = resolved_result(stage=2, reading_value=420.0, bands=(verified_band(stage=3),))
    request = request_for_resolution(result)
    payload = request.to_prompt_payload()
    assert payload["official_stage"] == "Stage II"
    assert payload["implied_stage"] == "Stage III"
    assert payload["stage_agreement"] == "DISCREPANCY"


def test_historical_replay_request_is_marked_replay():
    request = request_for_resolution(replay_result())
    assert request.mode == "REPLAY"
    assert request.replay_notice is not None
    assert request.kind is ExplanationKind.HISTORICAL_REPLAY


def test_unknown_fact_is_preserved_as_unknown():
    result = resolved_result(stage=3, facts={})
    request = request_for_resolution(result, kind=ExplanationKind.UNKNOWN_FACT)
    assert any(o.status == "unknown" for o in request.obligations)


def test_parchi_request_carries_state_but_no_worker_identity():
    parchi = parchi_domain(worker_id="wrk-secret-123", site_id="site-001")
    request = request_for_parchi(parchi)
    payload = request.to_prompt_payload()
    assert request.kind is ExplanationKind.PARCHI
    assert payload["parchi_status"] == "pending_ack"
    assert payload["parchi_ref"] == parchi.parchi_id
    assert "wrk-secret-123" not in json.dumps(payload)
