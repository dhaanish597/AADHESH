"""Publishing the `StageInvocation` event that starts the Standing Order machine.

The API Lambda does **not** call `states:StartExecution`, and that is a deliberate boundary
rather than an omission:

  * it holds `states:SendTaskSuccess` only, scoped to one state machine -- the resume path for a
    worker's acknowledgement, which must not be able to start a run;
  * it holds `events:PutEvents` on the default bus;
  * the `StageInvocation` EventBridge rule matches `source: aadesh.events`,
    `detail-type: StageInvocation`, and starts the machine itself, which is why
    `EventBridgeToStepFunctionsRole` exists separately from every function's role.

The consequence, and the reason the shape matters: what starts a workflow is a **published
event**, not a request. The trigger is visible in EventBridge, replayable on its own, and the
execution's input is the event's `detail` -- so an auditor can see what a run was started from
without reading the request that preceded it.

The publisher never fails the caller. A supervisor's Standing Order has already been signed and
its Parchis already opened by the time this runs; reporting that as a failed request would tell
a supervisor their signed pre-commitment does not exist. A failed publish is returned to the
caller instead, so the console can say plainly that the workflow did not start.
"""

from __future__ import annotations

import os
from typing import Any


def publish_stage_invocation(
    *,
    order_id: str,
    site_id: str,
    scenario: str,
    execution_id: str,
    stage: int | None = None,
    order_doc_id: str | None = None,
    order_sha256: str | None = None,
    bus_name: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Publish one `StageInvocation`. Returns what happened, never raises.

    `execution_id` is carried in the detail because the machine's `CreateParchis` step passes it
    to `open_parchis`. The API opened the Parchis under `exec-<order_id>` so a supervisor could
    show a QR inside the same request; the machine must use the SAME key, or its retry would
    mint a second set of Parchis for one trigger.

    `client` is injectable for the same reason `BedrockExplanationModel` and `S3Corpus` take
    one: a test must be able to exercise the publish decision without boto3 and without
    touching a real event bus.
    """
    detail: dict[str, Any] = {
        "order_id": order_id,
        "site_id": site_id,
        "scenario": scenario,
        "execution_id": execution_id,
    }
    if stage is not None:
        detail["stage"] = stage
    if order_doc_id is not None:
        detail["order_doc_id"] = order_doc_id
    if order_sha256 is not None:
        detail["order_sha256"] = order_sha256

    bus = bus_name or os.environ.get("AADESH_EVENT_BUS", "").strip() or "default"
    if client is None:
        try:
            import boto3

            client = boto3.client(
                "events", region_name=os.environ.get("AWS_REGION") or "ap-south-1"
            )
        except Exception as exc:
            return {"published": False, "reason": f"{type(exc).__name__}: {exc}"}

    try:
        import json

        response = client.put_events(
            Entries=[
                {
                    "Source": "aadesh.events",
                    "DetailType": "StageInvocation",
                    "EventBusName": bus,
                    "Detail": json.dumps(detail, sort_keys=True),
                }
            ]
        )
    except Exception as exc:
        return {"published": False, "reason": f"{type(exc).__name__}: {exc}"}

    failed = int(response.get("FailedEntryCount") or 0)
    if failed:
        errors = [
            str((entry.get("ErrorCode") or "") + " " + (entry.get("ErrorMessage") or "")).strip()
            for entry in response.get("Entries", [])
            if entry.get("ErrorCode")
        ]
        return {
            "published": False,
            "reason": "; ".join(errors) or f"{failed} event(s) were rejected by EventBridge",
        }
    return {"published": True, "event_id": (response.get("Entries") or [{}])[0].get("EventId")}


__all__ = ["publish_stage_invocation"]
