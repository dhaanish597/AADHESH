"""The deployed Step Functions machine must match the tested core machine.

If the ASL drifts from `aadesh_core.standing_order.machine.StandingOrderStep` and `advance()`,
this test fails. That is the point: the logic that gets tested is the logic that gets deployed.

We assert:
  * every StandingOrderStep value appears as a state name in the ASL;
  * the ASL's StartAt equals the first step;
  * the ASL's Next chain, read from the JSON, mirrors the successor chain the core machine
    produces for a representative payload.
"""

from __future__ import annotations

import json
from pathlib import Path

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.machine import StandingOrderStep, advance

ASL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "infra"
    / "stepfunctions"
    / "standing-order.asl.json"
)


def _load_asl() -> dict:
    return json.loads(ASL_PATH.read_text(encoding="utf-8"))


def _state_names(asl: dict) -> set[str]:
    return set(asl["States"].keys())


def _first_state(asl: dict) -> str:
    return asl["StartAt"]


def _next_chain(asl: dict, start: str) -> list[str]:
    chain: list[str] = []
    seen: set[str] = set()
    current = start
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        state = asl["States"][current]
        # Stop at terminal states (End: true, or no Next).
        if state.get("End") is True or "Next" not in state:
            break
        current = state["Next"]
    return chain


# --- state names ------------------------------------------------------------


def test_asl_contains_every_core_state() -> None:
    asl = _load_asl()
    core_states = {s.value for s in StandingOrderStep}
    asl_states = _state_names(asl)
    missing = core_states - asl_states
    assert not missing, f"core states not in ASL: {missing}"


def test_asl_start_at_is_the_first_step() -> None:
    asl = _load_asl()
    assert _first_state(asl) == StandingOrderStep.STAGE_TRIP.value


# --- Next chain --------------------------------------------------------------


def test_asl_next_chain_matches_core_successor_chain() -> None:
    """The ASL's Next chain should mirror the core machine's advance() chain for a successful run.

    The core machine's chain (successful case, no denials):

        StageTrip -> ResolveObligations -> Authorize -> CreateParchis -> PendingAck
          -> WorkerAcknowledgements -> SealParchis -> Audit

    The ASL's chain is read directly from the JSON's Next fields, stopping at the terminal state.
    """
    asl = _load_asl()
    asl_chain = _next_chain(asl, _first_state(asl))
    expected = [s.value for s in StandingOrderStep]
    assert asl_chain == expected, f"ASL chain {asl_chain} != core chain {expected}"


def test_core_advance_produces_the_same_chain_for_a_successful_run() -> None:
    """Follow advance() from StageTrip to Audit with a successful outcome at each step.

    The chain should be: StageTrip -> ResolveObligations -> Authorize -> CreateParchis ->
    PendingAck -> WorkerAcknowledgements -> SealParchis -> Audit.
    """
    state = StandingOrderStep.STAGE_TRIP
    chain = [state.value]
    payload: dict = {}
    expected_chain = [s.value for s in StandingOrderStep]
    # expected_chain[0] == StageTrip == chain[0]. Iterate from index 1.
    for i in range(1, len(expected_chain)):
        if state.value == StandingOrderStep.AUDIT.value:
            break
        payload = _outcome_for(state, payload)
        next_state, _ = advance(state=state, input=_input(payload), outcome=payload)
        assert next_state.value == expected_chain[i], (
            f"advance({state.value}) -> {next_state.value}, expected {expected_chain[i]}"
        )
        chain.append(next_state.value)
        state = next_state
    assert state.value == StandingOrderStep.AUDIT.value
    assert chain == expected_chain


def _outcome_for(state: StandingOrderStep, prior: dict) -> dict:
    if state is StandingOrderStep.STAGE_TRIP:
        return {
            "is_current": True,
            "invoked_stage": 3,
            "order_doc_id": "order-001",
            "order_sha256": "a" * 64,
            "site_id": "site-001",
        }
    if state is StandingOrderStep.RESOLVE_OBLIGATIONS:
        return {
            **prior,
            "obligation_ids": ("ob-1",),
            "entitlement_refs": (),
            "readiness_checklist": ("Welfare board registration number",),
            "displaced_worker_days": 1,
        }
    if state is StandingOrderStep.AUTHORIZE:
        return {
            **prior,
            "authorized": True,
            "reason": "supervisor is authorized for this site",
        }
    if state is StandingOrderStep.CREATE_PARCHIS:
        return {
            **prior,
            "parchi_ids": ("parchi-001",),
            "worker_ids": ("wrk-1",),
        }
    if state is StandingOrderStep.PENDING_ACK:
        return {
            **prior,
            "acknowledged": ("parchi-001",),
        }
    if state is StandingOrderStep.WORKER_ACKNOWLEDGEMENTS:
        return {
            **prior,
            "all_acknowledged": True,
            "acknowledged_ids": ("parchi-001",),
        }
    if state is StandingOrderStep.SEAL_PARCHIS:
        return {
            **prior,
            "sealed_ids": ("parchi-001",),
            "voided_ids": (),
            "sealed_count": 1,
        }
    # AUDIT -- the machine ends here.
    return {
        **prior,
        "status": StandingOrderStatus.COMPLETED,
        "completed_at": "2026-10-08T12:05:00+00:00",
        "audit": {"parchis_sealed": 1, "parchis_voided": 0},
    }


def _input(payload: dict) -> dict:
    return {
        "standing_order_id": "so-1",
        "fingerprint": "fp-1",
        "site_id": payload.get("site_id", "site-001"),
        "trigger_stage": 3,
        "order_doc_id": payload.get("order_doc_id", "order-001"),
        "order_sha256": payload.get("order_sha256", "a" * 64),
        "started_at": "2026-10-08T12:00:00+00:00",
    }


def test_asl_uses_waitForTaskToken_for_pending_ack() -> None:
    """The durable wait is lambda:invoke.waitForTaskToken, not a timer. Verify the ASL carries
    that resource in the PendingAck iterator."""
    asl = _load_asl()
    pending = asl["States"]["PendingAck"]
    iterator = pending["Iterator"]
    await_state = iterator["States"]["AwaitWorkerAck"]
    resource = await_state["Resource"]
    assert "waitForTaskToken" in resource, (
        f"PendingAck iterator must use waitForTaskToken, got {resource}"
    )
