"""Audit handler — Step Functions workflow final step.

Writes final audit record for Standing Order execution. Records all
steps: resolution, authorization, parchi creation, acknowledgments, sealing.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_SORDERS = os.environ.get("AADESH_TABLE_STANDING_ORDERS", "aadesh-standing-orders")
TABLE_PARCHIS = os.environ.get("AADESH_TABLE_PARCHIS", "aadesh-parchis")

_audit_log = boto3.client("logs", region_name=REGION)


def handle(event: dict, context: Any) -> dict:
    """Step Functions task — write audit record."""
    standing_order_id = event.get("standing_order_id", "unknown")
    site_id = event.get("site_id", "unknown")
    execution_id = event.get("execution_id", "unknown")

    audit_record = {
        "event_id": f"audit-{standing_order_id}-{datetime.now(UTC).timestamp()}",
        "standing_order_id": standing_order_id,
        "site_id": site_id,
        "execution_id": execution_id,
        "triggered_at": datetime.now(UTC).isoformat(),
        "workflow_status": event.get("status", "completed"),
        "parchi_count": event.get("parchi_count", 0),
        "acknowledged_count": event.get("acknowledged_count", 0),
        "sealed_count": event.get("sealed_count", 0),
        "resolution": event.get("resolution", {}),
        "authorization": event.get("authorization", {}),
    }

    # Write to CloudWatch Logs
    _write_audit_log(audit_record)

    # Update Standing Order status
    _update_standing_order_status(standing_order_id, "completed")

    return {
        "audit_record": audit_record,
        "status": audit_record["workflow_status"],
    }


def _write_audit_log(record: dict):
    """Write audit record to CloudWatch Logs."""
    try:
        _audit_log.put_log_events(
            logGroupName=f"/aws/lambda/aadesh-audit",
            logStreamName="audit",
            logEvents=[{
                "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                "message": json.dumps(record, default=str),
            }],
        )
    except Exception:
        pass  # Audit failure should not fail the workflow


def _update_standing_order_status(standing_order_id: str, status: str):
    """Update Standing Order status in DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_SORDERS)

    try:
        table.update_item(
            Key={"standing_order_id": standing_order_id},
            UpdateExpression="SET #s = :s, updated_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": status,
                ":t": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        pass
