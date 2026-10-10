"""The Step Functions step handlers.

Each function here is one state in the Standing Order machine, and each does one thing. They are
deliberately separate functions rather than one long handler because the machine is what makes
the workflow durable: a step can be retried, a step can wait for hours, and the execution
history shows exactly which step produced which fact.

The durable wait is the point of the whole machine. Between "Parchis opened" and "this worker
confirmed", there can be a shift change, a night, a next-morning walk back to the site. No
Lambda can hold that; `lambda:invoke.waitForTaskToken` can, and `task_waiter` is where the
token is parked meanwhile.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from aadesh_adapters.audit.cloudwatch import CloudWatchAuditLog
from aadesh_adapters.store.dynamo import (
    DynamoParchiStore,
    DynamoTaskTokenStore,
    table_name,
)
from aadesh_aws.runtime import Config, build_application, env_int
from aadesh_core.domain import ParchiState
from aadesh_core.parchi_ack import seal_parchi

# ---------------------------------------------------------------------------
# StageTrip -- what stage has actually been invoked, per the re-proved corpus
# ---------------------------------------------------------------------------


def stage_trip(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Read the invoked stage from the corpus. No arithmetic, no AQI input."""
    config = Config.from_env()
    scenario = str(event.get("scenario", "replay"))
    result = build_application(config).resolve(scenario=scenario)
    stage = result.stage
    return {
        "step": "StageTrip",
        "mode": result.mode.value,
        "stage": stage.stage if stage else None,
        "order_doc_id": stage.order_doc_id if stage else None,
        "order_sha256": stage.order_sha256 if stage else None,
        "lifecycle": stage.lifecycle.value if stage else None,
        "is_current": stage.is_current if stage else False,
        "replay_notice": result.replay_notice,
        "site_id": result.site_id,
    }


# ---------------------------------------------------------------------------
# Authorize -- re-check the pre-commitment is still valid at FIRE time
# ---------------------------------------------------------------------------


def authorize_standing_order(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Re-check that the signed order is still a valid pre-commitment right now.

    A Standing Order is signed days before it can fire, so "was it signed?" is not the question
    that matters at fire time -- "is it still in force?" is. This step recomputes the projected
    status from the stored validity window rather than trusting the status string that was
    written when it was signed, and fails the step (which the machine routes to Audit) when the
    window has closed or the order is no longer signed.
    """
    from aadesh_adapters.store.dynamo import DynamoStandingOrderStore
    from aadesh_core.standing_order import project_status

    order_id = str(event.get("order_id") or "")
    if not order_id:
        raise ValueError("authorize_standing_order requires order_id.")
    order = DynamoStandingOrderStore().get(order_id)
    if order is None:
        raise ValueError(f"Standing Order {order_id!r} is not in the store.")
    if not order.has_signed:
        raise ValueError(f"Standing Order {order_id!r} was never signed; it cannot fire.")
    status = project_status(order, now=datetime.now(UTC))
    if status.value not in ("active", "triggered"):
        raise ValueError(
            f"Standing Order {order_id!r} is {status.value}, so it is not eligible to fire. "
            f"Expiry closes an order from any non-terminal phase."
        )
    CloudWatchAuditLog().record(
        event="StandingOrderAuthorized",
        detail={
            "standing_order_id": order.standing_order_id,
            "site_id": order.site_id,
            "supervisor_id": order.supervisor_id,
            "projected_status": status.value,
            "commitment_hash": order.commitment_hash or "",
        },
    )
    return {
        "step": "Authorize",
        "authorized": True,
        "standing_order_id": order.standing_order_id,
        "supervisor_id": order.supervisor_id,
        "projected_status": status.value,
    }


# ---------------------------------------------------------------------------
# ResolveObligations -- which cited clauses apply, against the re-proved corpus
# ---------------------------------------------------------------------------


def resolve_obligations(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    config = Config.from_env()
    scenario = str(event.get("scenario", "replay"))
    result = build_application(config).resolve(scenario=scenario)
    issuing = [r for r in result.results if r.applicable is True and r.issues_parchi]
    return {
        "step": "ResolveObligations",
        "applicable": len(result.applicable),
        "fully_sourced": result.fully_sourced,
        "excluded": len(result.excluded_unsourced),
        "obligation_ids": sorted(r.obligation_id for r in issuing),
    }


# ---------------------------------------------------------------------------
# CreateParchis -- idempotent, on the same key the API used
# ---------------------------------------------------------------------------


def create_parchis(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Open the Parchis, or find the ones that already exist.

    Called with the same `execution_id` the API used when it opened the Parchis synchronously
    so the supervisor could show a QR within the same request. The shared key is what makes
    running twice safe: the second call returns the first call's records rather than minting a
    second set, which is the property `create_parchis_for_roster` exists to provide.
    """
    config = Config.from_env()
    app = build_application(config)
    execution_id = str(event.get("execution_id") or "")
    if not execution_id:
        raise ValueError(
            "create_parchis requires the execution_id the Parchis were opened under. Without "
            "it the call could mint a second set for the same trigger."
        )
    opened = app.open_parchis(
        scenario=str(event.get("scenario", "replay")),
        execution_id=execution_id,
    )
    # Two shapes of the same set, for two different consumers, and both are needed:
    #
    #   * `parchis` is what the Map iterates over -- one item per Parchi, each carrying the
    #     parchi id, the worker id and the site, which is exactly what a branch needs to park a
    #     task token against the right record;
    #   * `parchi_ids` is what the SealParchis step reads, because sealing is a run-level step
    #     over everything CreateParchis opened (the domain then seals only the acknowledged
    #     ones).
    return {
        "step": "CreateParchis",
        "execution_id": opened["execution_id"],
        "parchi_ids": [item["parchi_id"] for item in opened["parchis"]],
        "parchis": [
            {
                "parchi_id": item["parchi_id"],
                "worker_id": item["worker_id"],
                "site_id": config.site_id,
            }
            for item in opened["parchis"]
        ],
        "obligation_ids": opened["obligation_ids"],
    }


# ---------------------------------------------------------------------------
# AwaitWorkerAck -- park the task token, resume when the worker confirms
# ---------------------------------------------------------------------------


def worker_ack_waiter(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Store this execution's task token against the Parchi, then return.

    `lambda:invoke.waitForTaskToken` does NOT continue when this function returns; it continues
    only when somebody calls `SendTaskSuccess` with the token. So there are exactly two ways
    this state resolves, and both are handled here:

      * the worker has ALREADY confirmed (the common case in this deployment, where the API
        opens the Parchis and the machine picks them up moments later) -- then there is nothing
        to wait for, and the machine is resumed immediately;
      * the worker has not confirmed -- then the token is stored, and the acknowledgement path
        resumes the machine later.

    The re-read after storing closes the race in between. Without it, a confirmation landing
    between the first read and the write would find no token to signal, and the machine would
    sit until its timeout on a parchi that was already settled.
    """
    parchi_id = str(event.get("parchi_id") or "")
    task_token = str(event.get("task_token") or "")
    if not parchi_id or not task_token:
        raise ValueError("worker_ack_waiter requires parchi_id and task_token.")

    store = DynamoParchiStore()
    tokens = DynamoTaskTokenStore()

    settled = _settled(store.get(parchi_id))
    if settled:
        _resume(task_token, parchi_id, str(event.get("worker_id") or ""))
        return {"step": "AwaitWorkerAck", "parchi_id": parchi_id, "acknowledged": True}

    tokens.put(
        parchi_id=parchi_id,
        task_token=task_token,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=env_int("AADESH_ACK_WINDOW_SECONDS", 86400)),
    )

    settled = _settled(store.get(parchi_id))
    if settled:
        popped = tokens.pop(parchi_id=parchi_id)
        if popped is not None:
            # Nobody else claimed it, so this is the resume.
            _resume(popped, parchi_id, str(event.get("worker_id") or ""))
        return {"step": "AwaitWorkerAck", "parchi_id": parchi_id, "acknowledged": True}

    return {"step": "AwaitWorkerAck", "parchi_id": parchi_id, "waiting": True}


def _settled(parchi: Any) -> bool:
    return parchi is not None and parchi.state in (ParchiState.ACKNOWLEDGED, ParchiState.SEALED)


def _resume(task_token: str, parchi_id: str, worker_id: str) -> None:
    import json

    import boto3

    try:
        boto3.client("stepfunctions", region_name=_region()).send_task_success(
            taskToken=task_token,
            output=json.dumps(
                {"parchi_id": parchi_id, "worker_id": worker_id, "acknowledged": True}
            ),
        )
    except Exception:
        # The machine may already have timed out. The acknowledgement is a fact either way,
        # and it has already been written; failing here would misreport a settled parchi.
        return


# ---------------------------------------------------------------------------
# SealParchis -- freeze an acknowledged record over its content hash
# ---------------------------------------------------------------------------


def _created_parchi_ids(event: dict[str, Any]) -> list[Any]:
    """The Parchis CreateParchis opened, wherever the machine's ResultPath left them.

    The ASL writes that step's result to `$.parchis`, so the ids arrive nested -- unless a
    caller (a test, or a hand-run invocation) passes them at the top level, or names exactly
    one. Reading all three shapes here keeps the handler honest about the data rather than
    about one hard-coded path.
    """
    direct = event.get("parchi_ids")
    if direct:
        return list(direct)
    created = event.get("parchis")
    if isinstance(created, dict) and created.get("parchi_ids"):
        return list(created["parchi_ids"])
    single = event.get("parchi_id")
    return [single] if single else []


def seal_parchis(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Seal the Parchis that were confirmed. Refuses to seal anything else.

    The domain decides this, not this handler: `seal_parchi` refuses a PENDING_ACK parchi, so a
    machine retry can never produce a sealed record that no worker confirmed.
    """
    parchi_ids = _created_parchi_ids(event)
    if not parchi_ids:
        raise ValueError("seal_parchis requires parchi_ids or parchi_id.")

    store = DynamoParchiStore()
    audit = CloudWatchAuditLog()
    sealed: list[str] = []
    skipped: list[str] = []
    for parchi_id in parchi_ids:
        parchi = store.get(str(parchi_id))
        if parchi is None:
            skipped.append(str(parchi_id))
            continue
        if parchi.state is ParchiState.SEALED:
            skipped.append(parchi.parchi_id)
            continue
        if parchi.state is not ParchiState.ACKNOWLEDGED:
            # Not confirmed, so not evidence of anything yet. Left alone on purpose.
            skipped.append(parchi.parchi_id)
            continue
        seal_parchi(parchi=parchi, now=datetime.now(UTC), store=store, audit=audit)
        sealed.append(parchi.parchi_id)
    return {"step": "SealParchis", "sealed": sealed, "skipped": skipped}


# ---------------------------------------------------------------------------
# Audit -- one line that the run happened, and what it concluded
# ---------------------------------------------------------------------------


def audit(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    store = DynamoParchiStore()
    parchis = store.for_site(str(event.get("site_id") or Config.from_env().site_id))
    sealed = sum(1 for p in parchis if p.state is ParchiState.SEALED)
    acknowledged = sum(
        1 for p in parchis if p.state in (ParchiState.ACKNOWLEDGED, ParchiState.SEALED)
    )
    trip = event.get("trip") if isinstance(event.get("trip"), dict) else {}
    error = event.get("error")
    if isinstance(error, dict):
        # A Catcher's ResultPath writes the whole error object here. Flattening it keeps the
        # audit line one flat record, which is what the CloudWatch metric filter reads.
        error_text = str(error.get("Cause") or error.get("Error") or "")[:500]
    else:
        error_text = str(error or "")[:500]
    detail = {
        "execution_id": str(event.get("execution_id") or ""),
        "standing_order_id": str(event.get("order_id") or ""),
        "site_id": str(event.get("site_id") or ""),
        "stage": str(trip.get("stage", "")),
        "documented": len(parchis),
        "acknowledged": acknowledged,
        "sealed": sealed,
        "error": error_text,
    }
    CloudWatchAuditLog().record(event="StandingOrderWorkflowCompleted", detail=detail)
    return {"step": "Audit", **detail}


# ---------------------------------------------------------------------------
# Ingest -- the scheduled reading fetch
# ---------------------------------------------------------------------------


def ingest(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Fetch the nearest station reading and store it, or store nothing and say why.

    What this function will NOT do: invent a number. If no provider credentials are configured
    it records nothing, and says so. A readings table with a stale row in it is a smaller
    problem than a readings table with a fabricated row in it, because the fabricated row
    carries the same `provenance` label a real one would.
    """
    from aadesh_adapters.store.dynamo.readings import DynamoReadingsStore

    api_key = (event.get("openaq_api_key") if isinstance(event, dict) else None) or _env(
        "OPENAQ_API_KEY"
    )
    station_id = _env("AADESH_STATION_ID") or "DL-NCR-ROHINI-01"
    if not api_key:
        return {
            "step": "Ingest",
            "ingested": 0,
            "station_id": station_id,
            "reason": (
                "OPENAQ_API_KEY is not configured, so no live reading could be fetched. "
                "Nothing was written: Aadesh will not store a number it cannot attribute."
            ),
        }

    reading = _fetch_openaq(api_key, station_id)
    if reading is None:
        return {
            "step": "Ingest",
            "ingested": 0,
            "station_id": station_id,
            "reason": "The provider returned no usable measurement for this station.",
        }
    DynamoReadingsStore().put(reading)
    return {
        "step": "Ingest",
        "ingested": 1,
        "station_id": reading.station_id,
        "provenance": reading.provenance.value,
        "observed_at": reading.observed_at.isoformat(),
    }


def _fetch_openaq(api_key: str, station_id: str):
    """One measurement from OpenAQ v3, stamped MEASURED only if attributed."""
    import json
    import urllib.request

    from aadesh_core.domain import Provenance, StationReading

    base = _env("OPENAQ_BASE_URL") or "https://api.openaq.org/v3"
    url = f"{base}/stations/{station_id}/measurements?limit=1"
    request = urllib.request.Request(url, headers={"X-API-Key": api_key})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    results = payload.get("results") or []
    if not results:
        return None
    item = results[0]
    value = item.get("value")
    parameter = (item.get("parameter") or {}).get("name")
    observed = item.get("datetime", {}).get("utc")
    if value is None or not parameter or not observed:
        return None
    try:
        observed_at = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
    except ValueError:
        return None
    return StationReading(
        station_id=station_id,
        parameter=str(parameter),
        value=float(value),
        observed_at=observed_at,
        ingested_at=datetime.now(UTC),
        provenance=Provenance.MEASURED,
    )


def _env(name: str) -> str:
    import os

    return os.environ.get(name, "").strip()


def _region() -> str:
    return _env("AWS_REGION") or "ap-south-1"


__all__ = [
    "audit",
    "authorize_standing_order",
    "create_parchis",
    "ingest",
    "resolve_obligations",
    "seal_parchis",
    "stage_trip",
    "worker_ack_waiter",
]

# `table_name` is imported for the deployment check below: it fails loudly at import time if the
# environment names a table the stack does not create, rather than at the first write.
_TABLE_SANITY = table_name("parchis")
