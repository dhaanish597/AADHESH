"""INVARIANT: the model may not reference anything it was not given.

Grounding is the deterministic refusal of fabricated law and fabricated proof. Each test below
is a specific way a model could exceed its brief; each must be caught, returned as an
`UnsupportedReference`, and never silently accepted.
"""

from __future__ import annotations

from aadesh_core.explanation import check_grounding, request_for_resolution
from tests.support.explanation_builders import faithful_response, resolved_result


def request():
    return request_for_resolution(resolved_result(stage=3))


def test_a_faithful_response_is_fully_grounded():
    req = request()
    assert check_grounding(faithful_response(req), request=req) == []


def test_an_invented_citation_is_flagged():
    req = request()
    response = faithful_response(
        req,
        source_references=[{"source_doc": "invented-order", "page": 99}],
    )
    kinds = {u.kind for u in check_grounding(response, request=req)}
    assert "unknown-citation" in kinds


def test_an_invented_source_hash_is_flagged():
    req = request()
    real = req.citations[0]
    response = faithful_response(
        req,
        source_references=[
            {
                "source_doc": real.source_doc,
                "page": real.page,
                "source_hash": "f" * 64,
            }
        ],
    )
    kinds = {u.kind for u in check_grounding(response, request=req)}
    assert "invented-source-hash" in kinds


def test_an_invented_hash_in_prose_is_flagged():
    req = request()
    response = faithful_response(
        req,
        summary=f"This is backed by source hash {'b' * 64}.",
        source_references=[],
    )
    kinds = {u.kind for u in check_grounding(response, request=req)}
    assert "invented-source-hash" in kinds


def test_changing_the_official_stage_is_flagged():
    req = request()
    response = faithful_response(req, official_stage="Stage IV")
    kinds = {u.kind for u in check_grounding(response, request=req)}
    assert "stage-contradiction" in kinds


def test_changing_the_replay_status_is_flagged():
    req = request()
    response = faithful_response(req, replay_status="REPLAY")
    kinds = {u.kind for u in check_grounding(response, request=req)}
    assert "replay-contradiction" in kinds


def test_replaying_a_genuine_replay_response_stays_grounded():
    from tests.support.explanation_builders import replay_result

    req = request_for_resolution(replay_result())
    assert check_grounding(faithful_response(req), request=req) == []
