"""Step Functions task waiter — waits for worker acknowledgment.

Called by Step Functions waitForTaskToken. Holds state durably while
waiting for worker to scan QR and acknowledge. Signals workflow
to continue when acknowledgment received.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3

from aadesh_core.parchi_ack import AcknowledgementTokenStore
from aadesh_core.ports.parchi_store import DynamoDBParchiStore

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_PARCHIS = os.environ.get("AADESH_TABLE_PARCHIS", "aadesh-parchis")
STEP_FUNCTIONS_ARN = os.environ.get("STEP_FUNCTIONS_ARN", "")

_secrets = boto3.client("secretsmanager", region_name=REGION)


def handle(event: dict, context: Any) -> dict:
    """Wait for worker acknowledgment, then signal Step Functions."""
    parchi_id = event.get("parchi_id")
    worker_id = event.get("worker_id")
    task_token = event.get("task_token")

    if not task_token:
        return {"status": "error", "reason": "Missing task_token"}

    # Poll for acknowledgment with timeout
    store = DynamoDBParchiStore(boto3.resource("dynamodb", region_name=REGION), TABLE_PARCHIS)
    token_store = AcknowledgementTokenStore(
        dynamo=boto3.resource("dynamodb", region_name=REGION),
        table_name=TABLE_PARCHIS,
    )

    timeout = datetime.now(UTC) + timedelta(hours=24)  # 24-hour window
    poll_interval = 60  # seconds

    while datetime.now(UTC) < timeout:
        parchi = store.get(parchi_id)
        if parchi and parchi.state.value in ("acknowledged", "sealed"):
            # Signal Step Functions to continue
            _send_task_success(task_token, {
                "parchi_id": parchi_id,
                "worker_id": worker_id,
                "acknowledged": True,
                "state": parchi.state.value,
                "acknowledged_at": parchi.acknowledged_at.isoformat() if parchi.acknowledged_at else None,
                "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
            })
            return {"status": "acknowledged", "parchi_id": parchi_id}

        time.sleep(poll_interval)

    # Timeout — worker didn't acknowledge
    _send_task_success(task_token, {
        "parchi_id": parchi_id,
        "worker_id": worker_id,
        "acknowledged": False,
        "reason": "Worker did not acknowledge within the waiting window",
    })
    return {"status": "timeout", "parchi_id": parchi_id}


def _send_task_success(task_token: str, output: dict) -> None:
    """Signal Step Functions that the task is complete."""
    import boto3

    client = boto3.client("stepfunctions", region_name=REGION)
    client.send_task_success(
        taskToken=task_token,
        output=json.dumps(output),
    )


def _send_task_failure(task_token: str, error: str, cause: str) -> None:
    """Signal Step Functions that the task failed."""
    import boto3

    client = boto3.client("stepfunctions", region_name=REGION)
    client.send_task_failure(
        taskToken=task_token,
        error=error,
        cause=cause,
    )
