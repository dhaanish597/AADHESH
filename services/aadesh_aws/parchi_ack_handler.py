"""Parchi acknowledgment handler — worker confirms own Parchi.

Thin adapter: Cedar checks resource.worker == principal, domain checks again.
Idempotent by design. No proxy acknowledgement allowed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import boto3

from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import ACKNOWLEDGE_OWN_PARCHI
from aadesh_core.domain import Principal
from aadesh_core.ports.authz import CedarAuthorizationProvider
from aadesh_core.ports.parchi_store import DynamoDBParchiStore
from aadesh_core.ports.task_token import (
    DynamoDBAcknowledgementTokenStore,
    DynamoDbIdempotencyLedger,
)


REGION = _env("AWS_REGION", "ap-south-1")
TABLE_PARCHIS = _env("AADESH_TABLE_PARCHIS", "aadesh-parchis")
QR_SECRET = _env("AADESH_QR_SIGNING_SECRET", "change-me")
QR_TTL = int(_env("AADESH_QR_TOKEN_TTL_SECONDS", "86400"))
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
    """API Gateway handler for Parchi acknowledgment."""
    if event.get("httpMethod") == "OPTIONS":
        return _cors_response(204, {})

    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
    body = json.loads(event.get("body", "{}") or "{}")

    payload = body.get("payload", "")
    worker_id = body.get("worker_id", "")

    # Build principal — in production, from Cognito claims
    if claims:
        principal = Principal(
            principal_id=claims.get("sub", worker_id),
            role="worker",
        )
    else:
        principal = Principal(principal_id=worker_id, role="worker")

    try:
        outcome = _authz().acknowledge_own_parchi(
            principal=principal,
            payload=payload,
            now=datetime.now(UTC),
            store=_parchi_store(),
            tokens=_token_store(),
            ledger=_ledger(),
        )

        return _json_response(200, {
            "parchi": {
                "parchi_id": outcome.parchi.parchi_id,
                "site_id": outcome.parchi.site_id,
                "worker_id": outcome.parchi.worker_id,
                "state": outcome.parchi.state.value,
                "acknowledged_at": outcome.parchi.acknowledged_at.isoformat() if outcome.parchi.acknowledged_at else None,
                "sealed_at": outcome.parchi.sealed_at.isoformat() if outcome.parchi.sealed_at else None,
                "content_hash": outcome.parchi.content_hash,
            },
            "already_confirmed": outcome.already_confirmed,
            "event_id": outcome.event.event_id,
        })

    except Exception as e:
        # Cedar denial or domain refusal
        return _json_response(403, {
            "error": "Authorization denied",
            "reason": str(e),
        })


def _parchi_store() -> DynamoDBParchiStore:
    return DynamoDBParchiStore(_dynamo(), TABLE_PARCHIS)


def _token_store() -> DynamoDBAcknowledgementTokenStore:
    return DynamoDBAcknowledgementTokenStore(_dynamo(), TABLE_PARCHIS)


def _ledger() -> DynamoDbIdempotencyLedger:
    return DynamoDbIdempotencyLedger(_dynamo(), TABLE_PARCHIS)


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
