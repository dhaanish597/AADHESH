"""Parchi seal handler — Step Functions workflow step.

Seals acknowledged Parchis over content hash. Called after worker
acknowledgements complete in the workflow.
"""

from __future__ import annotations

import os
from typing import Any

import boto3

from aadesh_core.domain import ParchiState
from aadesh_core.ports.parchi_store import DynamoDBParchiStore

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_PARCHIS = os.environ.get("AADESH_TABLE_PARCHIS", "aadesh-parchis")


def handle(event: dict, context: Any) -> dict:
    """Step Functions task — seal acknowledged Parchis."""
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    store = DynamoDBParchiStore(dynamodb, TABLE_PARCHIS)

    parchi_ids = event.get("parchi_ids", [])
    acknowledged = event.get("acknowledgements", [])

    sealed = []
    for parchi_id in parchi_ids:
        parchi = store.get(parchi_id)
        if parchi and parchi.state.value == "acknowledged":
            parchi = parchi.seal()
            store.save(parchi)
            sealed.append({
                "parchi_id": parchi.parchi_id,
                "content_hash": parchi.content_hash,
                "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
            })

    return {
        "sealed": sealed,
        "count": len(sealed),
        "parchi_ids": parchi_ids,
    }
