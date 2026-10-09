"""Parchi creation handler — Step Functions workflow step.

Creates Parchis for all rostered workers when Standing Order triggers.
Part of the durable workflow: StageTrip → Resolve → Authorize → CreateParchis.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3

from aadesh_core.domain import ConstructionSite, Principal, InvokedStage, StationReading, Provenance
from aadesh_core.parchi_ack import Roster, RosterEntry, create_parchis_for_roster
from aadesh_core.parchi_ack.service import ParchiProvenance
from aadesh_core.ports.authz import CedarAuthorizationProvider
from aadesh_core.ports.parchi_store import DynamoDBParchiStore
from aadesh_core.ports.task_token import DynamoDBAcknowledgementTokenStore, DynamoDbIdempotencyLedger
from aadesh_core.stores import DynamoDBSitesStore

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_PARCHIS = os.environ.get("AADESH_TABLE_PARCHIS", "aadesh-parchis")
TABLE_SITES = os.environ.get("AADESH_TABLE_SITES", "aadesh-sites")
TABLE_SORDERS = os.environ.get("AADESH_TABLE_STANDING_ORDERS", "aadesh-standing-orders")


def handle(event: dict, context: Any) -> dict:
    """Step Functions task — create Parchis for workers."""
    site_id = event.get("site_id", "example-piling-site")
    execution_id = event.get("execution_id", "exec-demo-001")
    standing_order_id = event.get("standing_order_id", "")
    trigger_stage = event.get("trigger_stage", 3)

    dynamodb = boto3.resource("dynamodb", region_name=REGION)

    store = DynamoDBParchiStore(dynamodb, TABLE_PARCHIS)
    token_store = DynamoDBAcknowledgementTokenStore(dynamodb, TABLE_PARCHIS)
    ledger = DynamoDbIdempotencyLedger(dynamodb, TABLE_PARCHIS)
    sites_store = DynamoDBSitesStore(dynamodb, TABLE_SITES)

    # Get site
    site = sites_store.get(site_id)
    if site is None:
        site = ConstructionSite(
            site_id=site_id,
            activity_type="Piling works",
            project_category="Infrastructure",
        )
        sites_store.save(site)

    # Build roster
    roster = Roster(
        site_id=site_id,
        entries=tuple(
            RosterEntry(worker_id=f"worker-{i:03d}", display_name=f"Worker {i:03d}")
            for i in range(1, 35)
        ),
    )

    # Build provenance
    provenance = ParchiProvenance(
        stage=InvokedStage(
            stage=trigger_stage,
            invoked_at=datetime.now(UTC),
            lifecycle="active",
            order_doc_id=standing_order_id or "caqm-grap-2026-01",
            order_sha256="demo-hash",
        ),
        reading=StationReading(
            station_id="DL-NCR-ROHINI-01",
            parameter="PM2.5",
            value=285.0,
            observed_at=datetime.now(UTC) - timedelta(hours=1),
            ingested_at=datetime.now(UTC),
            provenance=Provenance.SYNTHETIC,
        ),
        obligation_ids=(
            "grap3-cnd-dust-01",
            "grap3-cnd-dust-02",
            "grap3-cnd-dust-03",
        ),
        entitlement_refs=(),
        readiness_checklist=(
            "Dust mitigation measures documented",
            "C&D waste management plan in place",
            "Commission directions complied with",
        ),
        displaced_worker_days=1,
    )

    # Create Parchis
    execution = {
        "execution_id": execution_id,
        "site_id": site_id,
    }

    issues = create_parchis_for_roster(
        execution=execution,
        roster=roster,
        provenance=provenance,
        idempotency_key=standing_order_id or "exec-demo-001",
        store=store,
        tokens=token_store,
        ledger=ledger,
    )

    return {
        "parchi_ids": [i.parchi.parchi_id for i in issues],
        "worker_ids": [i.parchi.worker_id for i in issues],
        "site_id": site_id,
        "execution_id": execution_id,
        "count": len(issues),
    }
