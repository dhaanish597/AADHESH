"""Obligation resolution handler — pure deterministic core.

Resolves obligations for a site against the verified corpus. No model,
no network beyond AWS SDK for persistence. Returns obligation set with
citations. Same core the CLI and local API use.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3

from aadesh_core.domain import ConstructionSite, Principal, SiteResource
from aadesh_core.ports.authz import CedarAuthorizationProvider
from aadesh_core.resolver import resolve_obligations
from aadesh_core.stores import DynamoDBSitesStore

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_SITES = os.environ.get("AADESH_TABLE_SITES", "aadesh-sites")
POLICY_PATH = "/var/task/infra/cedar/policies.cedar"


def handle(event: dict, context: Any) -> dict:
    """API Gateway handler for obligation resolution."""
    if event.get("httpMethod") == "OPTIONS":
        return _cors_response(204, {})

    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
    body = json.loads(event.get("body", "{}") or "{}")

    site_id = body.get("site_id", claims.get("assigned_site", "example-piling-site"))
    scenario = body.get("scenario", "current")

    try:
        result = _resolve(site_id, scenario)
        return _json_response(200, _format_result(result))
    except Exception as e:
        return _error_response(500, str(e))


def _resolve(site_id: str, scenario: str):
    """Resolve obligations for a site."""
    from aadesh_core.ports.corpus import LocalFileCorpus

    sites_store = DynamoDBSitesStore(boto3.resource("dynamodb", region_name=REGION), TABLE_SITES)
    corpus = LocalFileCorpus("/var/task/corpus" if os.path.exists("/var/task/corpus") else os.path.join(os.path.dirname(__file__), "../../corpus"))

    # Load or create site
    site = sites_store.get(site_id)
    if site is None:
        site = ConstructionSite(
            site_id=site_id,
            activity_type="Piling works",
            project_category="Infrastructure",
        )
        sites_store.save(site)

    # Determine replay context
    replay = None
    if scenario == "replay":
        from aadesh_core.domain import ReplayContext
        replay = ReplayContext(
            invocation_date="2026-01-16",
            revocation_date="2026-01-22",
        )

    # Get reading
    reading = _get_reading()

    return resolve_obligations(
        site=site,
        corpus=corpus.snapshot(),
        now=datetime.now(UTC),
        replay=replay,
        reading=reading,
    )


def _get_reading():
    """Get latest reading from DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(os.environ.get("AADESH_TABLE_READINGS", "aadesh-readings"))

    try:
        result = table.query(
            KeyConditionExpression="station_id = :sid",
            ExpressionAttributeValues={":sid": os.environ.get("AADESH_STATION_ID", "DL-NCR-ROHINI-01")},
            ScanIndexForward=False,
            Limit=1,
        )
        items = result.get("Items", [])
        if items:
            item = items[0]
            from aadesh_core.domain import Provenance, StationReading
            return StationReading(
                station_id=item["station_id"],
                parameter=item["parameter"],
                value=float(item["value"]),
                observed_at=datetime.fromisoformat(item["observed_at"]),
                ingested_at=datetime.fromisoformat(item["ingested_at"]),
                provenance=Provenance(item["provenance"]),
            )
    except Exception:
        pass

    # Fallback to synthetic
    from aadesh_core.domain import Provenance, StationReading
    return StationReading(
        station_id="DL-NCR-ROHINI-01",
        parameter="PM2.5",
        value=285.0,
        observed_at=datetime.now(UTC) - timedelta(hours=1),
        ingested_at=datetime.now(UTC),
        provenance=Provenance.SYNTHETIC,
    )


def _format_result(result) -> dict:
    """Format resolution result for API response."""
    from aadesh_core.resolver import resolution_to_dict

    payload = resolution_to_dict(result)

    # Add site info
    payload["site"] = {
        "site_id": result.site_id,
        "label": "Construction Site",
        "activity_type": result.site.activity_type,
        "project_category": result.site.project_category,
    }

    # Add stage detail
    payload["stage_detail"] = {
        "official_stage": result.stage.stage if result.stage else "NONE",
        "is_replay": result.mode.value == "REPLAY",
        "lifecycle": result.stage.lifecycle.value if result.stage else None,
        "order_doc_id": result.stage.order_doc_id if result.stage else None,
        "discrepancy": result.stage_status.status.value == "DISCREPANCY",
    }

    # Add reading info
    if result.reading:
        from datetime import timedelta
        age = datetime.now(UTC) - result.reading.observed_at
        payload["reading"]["age_minutes"] = int(age.total_seconds() // 60)
        payload["reading"]["freshness"] = "FRESH" if age <= timedelta(minutes=90) else "STALE"

    return payload


def _cors_response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _json_response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _error_response(status: int, reason: str) -> dict:
    return _json_response(status, {"error": reason})
