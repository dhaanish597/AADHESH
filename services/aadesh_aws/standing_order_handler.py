"""Standing Order handler — create/manage Standing Orders with Cedar authz.

Thin adapter: authorizes via Cedar, then delegates to aadesh_core domain.
No business logic of its own.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import boto3

from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import ISSUE_HALT
from aadesh_core.domain import Principal
from aadesh_core.ports.authz import CedarAuthorizationProvider
from aadesh_core.stores import DynamoDBSitesStore, DynamoDBStandingOrdersStore
from aadesh_core.standing_order import (
    StandingOrder,
    activate,
    confirm,
    create,
    project_status,
)

REGION = _env("AWS_REGION", "ap-south-1")
TABLE_SITES = _env("AADESH_TABLE_SITES", "aadesh-sites")
TABLE_SORDERS = _env("AADESH_TABLE_STANDING_ORDERS", "aadesh-standing-orders")
POLICY_PATH = "/var/task/infra/cedar/policies.cedar"
DENIALS_PATH = "/var/task/infra/cedar/denials.json"


def _env(name: str, default: str = "") -> str:
    import os
    return os.environ.get(name, default)


def _dynamo():
    return boto3.resource("dynamodb", region_name=REGION)


def _authz():
    return AuthorizationService(
        authz=CedarAuthorizationProvider(
            policy_path=POLICY_PATH,
            denials_path=DENIALS_PATH,
        )
    )


def handle(event: dict, context: Any) -> dict:
    """API Gateway handler for Standing Order operations."""
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})

    if event.get("httpMethod") == "OPTIONS":
        return _cors_response(204, {})

    body = json.loads(event.get("body", "{}") or "{}")
    path = event.get("path", "")
    action = body.get("action", "create")

    try:
        if action == "create":
            return _create_standing_order(body, claims)
        elif action == "view":
            return _view_standing_order(body, claims)
        elif action == "list":
            return _list_standing_orders(claims)
        else:
            return _error_response(400, f"Unknown action: {action}")
    except Exception as e:
        return _error_response(500, str(e))


def _create_standing_order(body: dict, claims: dict) -> dict:
    """Create a new Standing Order."""
    authz = _authz()
    sites_store = DynamoDBSitesStore(_dynamo(), TABLE_SITES)
    sorders_store = DynamoDBStandingOrdersStore(_dynamo(), TABLE_SORDERS)

    # Get or create site
    site_id = body.get("site_id", "example-piling-site")
    site = sites_store.get(site_id)
    if site is None:
        from aadesh_core.domain.construction import ConstructionSite
        site = ConstructionSite(
            site_id=site_id,
            activity_type=body.get("activity_type", "Piling works"),
            project_category=body.get("project_category", "Infrastructure"),
        )
        sites_store.save(site)

    # Build principal from claims or demo
    if claims:
        principal = Principal(
            principal_id=claims.get("sub", "unknown"),
            role="supervisor",
            assigned_site=site_id,
        )
    else:
        principal = Principal(
            principal_id="supervisor-001",
            role="supervisor",
            assigned_site=site_id,
        )

    now = datetime.now(UTC)

    # Authorize
    authz.require_issue_halt(principal=principal, site_id=site_id, now=now)

    # Create Standing Order
    order = create(
        site_id=site_id,
        supervisor_id=principal.principal_id,
        trigger_stage=body.get("trigger_stage", 3),
        trigger_match=body.get("trigger_match", "exact"),
        actions=[
            ("ISSUE_HALT", {}),
            ("OPEN_PARCHI_PER_WORKER", {}),
        ],
        valid_from=now,
        valid_until=now.replace(day=now.day + 7),
        status="DRAFT",
    )

    # Confirm and activate
    order = confirm(order, supervisor_id=principal.principal_id, now=now)
    order = activate(order, now=now)

    # Persist
    sorders_store.save(order)

    return _json_response(200, {
        "standing_order": _order_to_dict(order, now),
        "status": "created",
    })


def _view_standing_order(body: dict, claims: dict) -> dict:
    """View a specific Standing Order."""
    sorders_store = DynamoDBStandingOrdersStore(_dynamo(), TABLE_SORDERS)
    order_id = body.get("standing_order_id")
    order = sorders_store.get(order_id)

    if order is None:
        return _error_response(404, "Standing Order not found")

    return _json_response(200, {"standing_order": _order_to_dict(order, datetime.now(UTC))})


def _list_standing_orders(claims: dict) -> dict:
    """List Standing Orders for the authenticated user's site."""
    sorders_store = DynamoDBStandingOrdersStore(_dynamo(), TABLE_SORDERS)

    if claims:
        site_id = claims.get("assigned_site")
    else:
        site_id = "example-piling-site"

    orders = sorders_store.for_site(site_id)

    return _json_response(200, {
        "standing_orders": [_order_to_dict(o, datetime.now(UTC)) for o in orders],
    })


def _order_to_dict(order: StandingOrder, now: datetime) -> dict:
    return {
        "standing_order_id": order.standing_order_id,
        "site_id": order.site_id,
        "supervisor_id": order.supervisor_id,
        "trigger": {
            "stage": order.trigger.stage,
            "match": order.trigger.match.value,
            "type": order.trigger.type.value,
        },
        "actions": [
            {"action": a.action.value, "parameters": dict(a.parameters)}
            for a in order.actions
        ],
        "valid_from": order.valid_from.isoformat(),
        "valid_until": order.valid_until.isoformat(),
        "status": order.status.value,
        "projected_status": project_status(order, now=now).value,
        "created_at": order.created_at.isoformat(),
        "signed_at": order.signed_at.isoformat() if order.signed_at else None,
        "commitment_hash": order.commitment_hash,
        "trigger_fingerprint": order.trigger_fingerprint,
    }


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
