"""Stage trip handler — Step Functions first step.

Determines the invoked stage from the corpus and event context.
Does NOT compute from AQI — stage comes from CAQM order.
"""

from __future__ import annotations

import os
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_SITES = os.environ.get("AADESH_TABLE_SITES", "aadesh-sites")


def handle(event: dict, context: Any) -> dict:
    """Step Functions task — determine invoked stage."""
    site_id = event.get("site_id", "example-piling-site")
    event_id = event.get("event_id", "stage-trip")

    # In the real system, this would look up the invoked stage from
    # the corpus (which contains the CAQM order that invoked the stage).
    # For demo, we use the historical Stage III invocation.

    return {
        "stage": 3,
        "invoked_at": "2026-01-16T00:00:00Z",
        "order_doc_id": "caqm-grap-2026-01",
        "order_sha256": "demo-hash",
        "lifecycle": "active",
        "site_id": site_id,
        "event_id": event_id,
        "is_current": False,  # Historical replay — not current
    }
