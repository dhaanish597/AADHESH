"""Step Functions successor for the standing-order machine.

The machine is a pure function of state + event. The committed ASL in
`infra/stepfunctions/standing-order.asl.json` is the deployed shape; this module is the tested
shape; `test_asl_matches_core_machine.py` asserts they agree, so a deployed machine cannot drift
from the logic that was tested.

State names match StandingOrderStep exactly, including PENDING_ACK (the durable wait). The
machine survives waiting: each state is a checkpoint, not a timer. Nothing here reads the clock
or decides whether a trigger fires -- that is the trigger module's job. The machine starts when
`evaluate_trigger` says fires=True and `TriggerRunStore.claim` returns a run (new or existing).

Lifecycle of the machine, durably:

    StageTrip -> ResolveObligations -> Authorize -> CreateParchis
        -> PendingAck -> WorkerAcknowledgements -> SealParchis -> Audit

PENDING_ACK is a Map over the created parchis, each branch a
`lambda:invoke.waitForTaskToken` task. Step Functions holds the token; nothing polls. A worker
scanning their QR three hours after another worker resumes only resumes their own branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import StandingOrder, TriggerRun


class StandingOrderStep(StrEnum):
    """State names in the Step Functions machine. Must equal the ASL's state names."""

    STAGE_TRIP = "StageTrip"
    RESOLVE_OBLIGATIONS = "ResolveObligations"
    AUTHORIZE = "Authorize"
    CREATE_PARCHIS = "CreateParchis"
    PENDING_ACK = "PendingAck"
    WORKER_ACKNOWLEDGEMENTS = "WorkerAcknowledgements"
    SEAL_PARCHIS = "SealParchis"
    AUDIT = "Audit"


@dataclass(frozen=True, slots=True)
class MachineInput:
    """The event the machine receives when it starts."""

    standing_order_id: str
    fingerprint: str
    site_id: str
    trigger_stage: int
    order_doc_id: str
    order_sha256: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class MachineOutput:
    """The terminal result of the machine, after Audit."""

    standing_order_id: str
    fingerprint: str
    status: StandingOrderStatus
    parchi_ids: tuple[str, ...]
    sealed_count: int
    completed_at: datetime
    audit: dict[str, Any]


def advance(
    *,
    state: StandingOrderStep,
    input: MachineInput,
    outcome: dict[str, Any],
) -> tuple[StandingOrderStep, dict[str, Any]]:
    """Pure successor: given the current state and the outcome of the previous step, return the
    next state and the payload to pass to it.

    `outcome` is the output of the step that just finished. For terminal states, return the state
    itself with an empty payload.
    """
    if state is StandingOrderStep.STAGE_TRIP:
        return _stage_trip(payload=outcome)
    if state is StandingOrderStep.RESOLVE_OBLIGATIONS:
        return _resolve_obligations(payload=outcome)
    if state is StandingOrderStep.AUTHORIZE:
        return _authorize(payload=outcome)
    if state is StandingOrderStep.CREATE_PARCHIS:
        return _create_parchis(payload=outcome)
    if state is StandingOrderStep.PENDING_ACK:
        return _pending_ack(payload=outcome)
    if state is StandingOrderStep.WORKER_ACKNOWLEDGEMENTS:
        return _worker_acknowledgements(payload=outcome)
    if state is StandingOrderStep.SEAL_PARCHIS:
        return _seal_parchis(payload=outcome)
    if state is StandingOrderStep.AUDIT:
        return _audit(payload=outcome)
    raise RuntimeError(f"unknown machine state: {state.value}")


# --- step outcomes -----------------------------------------------------------


def _stage_trip(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """StageTrip loads the invoked stage from the corpus and confirms it is current.

    Outcome shape: {invoked_stage: int, order_doc_id: str, order_sha256: str, site_id: str,
    is_current: bool}
    """
    if not payload.get("is_current"):
        raise RuntimeError("StageTrip: the invoking order is not current; stopping the machine.")
    return (
        StandingOrderStep.RESOLVE_OBLIGATIONS,
        {
            "site_id": payload["site_id"],
            "order_doc_id": payload["order_doc_id"],
            "order_sha256": payload["order_sha256"],
            "invoked_stage": payload["invoked_stage"],
        },
    )


def _resolve_obligations(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """ResolveObligations runs the deterministic resolver for the site at the time of the trigger.

    Outcome shape: {obligation_ids: tuple[str, ...], entitlement_refs: tuple[str, ...],
    readiness_checklist: tuple[str, ...], displaced_worker_days: int}
    """
    return (
        StandingOrderStep.AUTHORIZE,
        {
            "site_id": payload["site_id"],
            "obligation_ids": payload.get("obligation_ids", ()),
            "entitlement_refs": payload.get("entitlement_refs", ()),
            "readiness_checklist": payload.get("readiness_checklist", ()),
            "displaced_worker_days": payload.get("displaced_worker_days", 0),
            "order_doc_id": payload["order_doc_id"],
            "order_sha256": payload["order_sha256"],
            "invoked_stage": payload["invoked_stage"],
        },
    )


def _authorize(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """Authorize re-checks the recorded supervisor's authority at fire time, not at signing time.

    Outcome shape: {authorized: bool, reason: str}
    If not authorized, the machine stops before CreateParchis and no parchi exists to clean up.
    """
    if not payload.get("authorized"):
        raise RuntimeError(
            f"Authorize: {payload.get('reason', 'not authorized')}. Stopping the machine."
        )
    return (
        StandingOrderStep.CREATE_PARCHIS,
        {
            "site_id": payload["site_id"],
            "obligation_ids": payload["obligation_ids"],
            "entitlement_refs": payload["entitlement_refs"],
            "readiness_checklist": payload["readiness_checklist"],
            "displaced_worker_days": payload["displaced_worker_days"],
            "order_doc_id": payload["order_doc_id"],
            "order_sha256": payload["order_sha256"],
            "invoked_stage": payload["invoked_stage"],
        },
    )


def _create_parchis(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """CreateParchis opens one DRAFT parchi per rostered worker for the site.

    Outcome shape: {parchi_ids: tuple[str, ...], worker_ids: tuple[str, ...]}
    The parchi ids are deterministic from (fingerprint, worker_id). A redelivery computes the
    same ids and therefore collides on save.
    """
    return (
        StandingOrderStep.PENDING_ACK,
        {
            "parchi_ids": payload["parchi_ids"],
            "worker_ids": payload["worker_ids"],
        },
    )


def _pending_ack(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """PendingAck is a durable wait per parchi. In Step Functions it is a Map over parchi_ids,
    each branch a lambda:invoke.waitForTaskToken task. Here we just pass the set forward.

    Outcome shape: {acknowledged: tuple[str, ...]}  (the parchi_ids the workers acknowledged)
    """
    return (
        StandingOrderStep.WORKER_ACKNOWLEDGEMENTS,
        {
            "parchi_ids": payload["parchi_ids"],
            "worker_ids": payload["worker_ids"],
            "acknowledged": payload.get("acknowledged", ()),
        },
    )


def _worker_acknowledgements(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """WorkerAcknowledgements collects the acknowledgements gathered during the wait.

    Outcome shape: {all_acknowledged: bool, acknowledged_ids: tuple[str, ...]}
    """
    return (
        StandingOrderStep.SEAL_PARCHIS,
        {
            "parchi_ids": payload["parchi_ids"],
            "worker_ids": payload["worker_ids"],
            "acknowledged_ids": payload.get("acknowledged_ids", ()),
            "all_acknowledged": payload.get("all_acknowledged", False),
        },
    )


def _seal_parchis(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """SealParchis seals every parchi that was acknowledged (and voids the rest).

    Outcome shape: {sealed_ids: tuple[str, ...], voided_ids: tuple[str, ...],
    sealed_count: int}
    """
    return (
        StandingOrderStep.AUDIT,
        {
            "sealed_ids": payload.get("sealed_ids", ()),
            "voided_ids": payload.get("voided_ids", ()),
            "sealed_count": payload.get("sealed_count", 0),
            "parchi_ids": payload["parchi_ids"],
        },
    )


def _audit(payload: dict[str, Any]) -> tuple[StandingOrderStep, dict[str, Any]]:
    """Audit records the terminal outcome. The machine ends here.

    Outcome shape: {status: StandingOrderStatus, completed_at: datetime, audit: dict}
    """
    return (StandingOrderStep.AUDIT, {})


# --- machine entry -----------------------------------------------------------


def start_machine(
    *,
    order: StandingOrder,
    run: TriggerRun,
    now: datetime,
) -> MachineInput:
    """Build the MachineInput the Step Functions execution starts from.

    Pure. The caller (the trigger adapter or the Step Functions start execution API) is
    responsible for actually starting the execution. This just assembles the input.
    """
    return MachineInput(
        standing_order_id=order.standing_order_id,
        fingerprint=run.fingerprint,
        site_id=order.site_id,
        trigger_stage=order.trigger.stage,
        order_doc_id=run.order_doc_id,
        order_sha256=run.order_sha256,
        started_at=run.started_at,
    )
