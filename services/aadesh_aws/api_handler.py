"""API Gateway handler — routes HTTP to aadesh_core domain operations.

This is the thin adapter the frontend calls. It knows about API Gateway
events and DynamoDB/Lambda specifics, but every decision comes from
aadesh_core. Same core the CLI, local API, and tests use.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from cedarpy import policies_to_json_str

from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import (
    ASSIST_CLAIM,
    ISSUE_HALT,
    VIEW_PARCHI,
    VIEW_SITE_EXECUTION,
)
from aadesh_core.consent import grant_consent, request_assistance
from aadesh_core.domain import Principal, PrincipalResource, SiteResource
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack import (
    Roster,
    RosterEntry,
    create_parchis_for_roster,
)
from aadesh_core.parchi_ack.service import (
    acknowledge_parchi,
    describe_pending_parchi,
    resolve_parchi_for_payload,
)
from aadesh_core.ports.authz import CedarAuthorizationProvider, EntityRef
from aadesh_core.ports.parchi_store import DynamoDBParchiStore
from aadesh_core.ports.task_token import (
    DynamoDBAcknowledgementTokenStore,
    DynamoDbIdempotencyLedger,
)
from aadesh_core.resolver import resolve_obligations
from aadesh_core.standing_order import (
    StandingOrder,
    activate,
    confirm,
    create,
)
from aadesh_core.stores import DynamoDBSitesStore, DynamoDBStandingOrdersStore
from aadesh_core.vectors import LocalFileCorpus

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

REGION = _env("AWS_REGION", "ap-south-1")
TABLE_PARCHIS = _env("AADESH_TABLE_PARCHIS", "aadesh-parchis")
TABLE_READINGS = _env("AADESH_TABLE_READINGS", "aadesh-readings")
TABLE_SORDERS = _env("AADESH_TABLE_STANDING_ORDERS", "aadesh-standing-orders")
TABLE_SITES = _env("AADESH_TABLE_SITES", "aadesh-sites")
SOURCE_BUCKET = _env("AADESH_SOURCE_BUCKET", "aadesh-corpus")
POLICY_PATH = Path(_env("AADESH_CEDAR_POLICY_PATH", "infra/cedar/policies.cedar"))
DENIALS_PATH = Path(_env("AADESH_CEDAR_DENIALS_PATH", "infra/cedar/denials.json"))
SCHEMA_PATH = Path(_env("AADESH_CEDAR_SCHEMA_PATH", "infra/cedar/schema.cedarschema.json"))
QR_SECRET = _env("AADESH_QR_SIGNING_SECRET", "change-me-not-a-real-secret")
QR_TTL = int(_env("AADESH_QR_TOKEN_TTL_SECONDS", "86400"))
ENV = _env("AADESH_ENV", "aws")
STATION_ID = _env("AADESH_STATION_ID", "")
READING_STALENESS = int(_env("AADESH_READING_STALENESS_SECONDS", "5400"))

# Default demo constants — same as local server for consistency
SITE_ID = "example-piling-site"
SITE_LABEL = "Construction Site — Delhi-NCR"
SUPERVISOR_ID = "supervisor-001"
FACILITATOR_ID = "facilitator-001"
WORKER_COUNT = 34
REGISTERED_WORKERS = 27

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_dynamodb = None


def _dynamo():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=REGION)
    return _dynamodb


def _env(name: str, default: str = "") -> str:
    import os
    return os.environ.get(name, default)


def _now() -> datetime:
    return datetime.now(UTC)


def _json_body(event: dict) -> dict:
    try:
        return json.loads(event.get("body", "{}") or "{}")
    except json.JSONDecodeError:
        return {}


def _query_params(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    return {k: v for k, v in params.items() if v is not None}


def _cognito_claims(event: dict) -> dict | None:
    """Extract Cognito claims from API Gateway authorizer context."""
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    claims = authorizer.get("claims") or {}
    return claims


def _principal_from_claims(claims: dict | None, role: str) -> Principal:
    """Build a Principal from Cognito claims. In production, claims contain
    the real user. In demo, we use fixture principals."""
    if claims:
        user_id = claims.get("sub", "")
        assigned_site = claims.get("assigned_site") or None
        return Principal(
            principal_id=user_id,
            role=role,
            assigned_site=assigned_site,
        )
    # Fallback to demo principals for unauthenticated/dev scenarios
    if role == "supervisor":
        return Principal(principal_id=SUPERVISOR_ID, role="supervisor", assigned_site=SITE_ID)
    elif role == "facilitator":
        return Principal(principal_id=FACILITATOR_ID, role="facilitator")
    return Principal(principal_id="worker-demo", role="worker")


# ---------------------------------------------------------------------------
# Store factories
# ---------------------------------------------------------------------------

def _parchi_store() -> DynamoDBParchiStore:
    return DynamoDBParchiStore(
        dynamo=_dynamo(),
        table_name=TABLE_PARCHIS,
    )


def _token_store() -> DynamoDBAcknowledgementTokenStore:
    return DynamoDBAcknowledgementTokenStore(
        dynamo=_dynamo(),
        table_name=TABLE_PARCHIS,  # tokens stored alongside parchis
    )


def _ledger() -> DynamoDbIdempotencyLedger:
    return DynamoDbIdempotencyLedger(
        dynamo=_dynamo(),
        table_name=TABLE_PARCHIS,
    )


def _sites_store() -> DynamoDBSitesStore:
    return DynamoDBSitesStore(
        dynamo=_dynamo(),
        table_name=TABLE_SITES,
    )


def _standing_orders_store() -> DynamoDBStandingOrdersStore:
    return DynamoDBStandingOrdersStore(
        dynamo=_dynamo(),
        table_name=TABLE_SORDERS,
    )


def _corpus():
    """Load corpus from S3 or local path."""
    import os
    backend = os.environ.get("AADESH_CORPUS_BACKEND", "local")
    if backend == "s3" and SOURCE_BUCKET:
        from aadesh_adapters.corpus.s3 import S3Corpus
        return S3Corpus(bucket=SOURCE_BUCKET)
    return LocalFileCorpus(Path("/var/task/corpus") if Path("/var/task/corpus").exists() else Path(__file__).parent.parent / "corpus")


def _authz_provider():
    return CedarAuthorizationProvider(
        policy_path=POLICY_PATH,
        denials_path=DENIALS_PATH,
        schema_path=SCHEMA_PATH,
    )


def _authz_service():
    return AuthorizationService(authz=_authz_provider())


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def handle(event: dict, context: Any) -> dict:
    """API Gateway proxy integration handler."""
    # Handle preflight
    if event.get("httpMethod") == "OPTIONS":
        return _cors_response(204, {})

    path = event.get("path", "")
    http_method = event.get("httpMethod", "GET")

    try:
        if http_method == "GET":
            return _handle_get(path, event)
        elif http_method == "POST":
            return _handle_post(path, event)
        else:
            return _error_response(405, "Method not allowed")
    except Exception as e:
        return _error_response(500, str(e))


def _handle_get(path: str, event: dict) -> dict:
    params = _query_params(event)
    claims = _Cognito_claims(event)

    if path == "/api/health":
        return _health_get()

    elif path == "/api/supervisor":
        scenario = params.get("scenario", "replay")
        reading = params.get("reading", "aligned")
        principal = _principal_from_claims(claims, "supervisor")
        return _supervisor_get(principal, scenario, reading)

    elif path == "/api/roster":
        return _roster_get()

    elif path == "/api/roster/qr":
        scenario = params.get("scenario", "replay")
        return _roster_qr_get(scenario)

    elif path == "/api/facilitator":
        return _facilitator_get()

    elif path == "/api/verify":
        return _verify_get()

    elif path == "/api/impact":
        return _impact_get()

    elif path.startswith("/api/parchi/"):
        parchi_id = path.split("/")[-1]
        principal = _principal_from_claims(claims, "supervisor")
        return _parchi_get(principal, parchi_id)

    return _error_response(404, f"Not found: {path}")


def _handle_post(path: str, event: dict) -> dict:
    body = _json_body(event)
    claims = _Cognito_claims(event)

    if path == "/api/standing-order":
        scenario = body.get("scenario", "replay")
        principal = _principal_from_claims(claims, "supervisor")
        return _standing_order_post(principal, scenario)

    elif path == "/api/worker/view":
        payload = str(body.get("payload", ""))
        return _worker_view_post(payload)

    elif path == "/api/worker/acknowledge":
        payload = str(body.get("payload", ""))
        worker_id = str(body.get("worker_id", ""))
        principal = _principal_from_claims(claims, "worker")
        return _worker_acknowledge_post(principal, payload, worker_id)

    elif path == "/api/cedar/supervisor-acknowledge":
        worker_id = str(body.get("worker_id", "worker-001"))
        principal = _principal_from_claims(claims, "supervisor")
        return _cedar_supervisor_acknowledge(principal, worker_id)

    elif path == "/api/assist":
        worker_id = str(body.get("worker_id", ""))
        parchi_id = str(body.get("parchi_id", ""))
        principal = _principal_from_claims(claims, "facilitator")
        return _assist_post(principal, worker_id, parchi_id)

    return _error_response(404, f"Not found: {path}")


# ---------------------------------------------------------------------------
# GET handlers
# ---------------------------------------------------------------------------


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
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
        },
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _error_response(status: int, reason: str) -> dict:
    return _json_response(status, {"error": reason})


def _health_get() -> dict:
    authz = _authz_provider()
    validation = authz.validate()
    return _json_response(200, {
        "status": "ok",
        "instance": "aws-lambda",
        "region": REGION,
        "environment": ENV,
        "cedar_actions": sorted(authz.known_actions),
        "cedar_policy_errors": validation,
    })


def _supervisor_get(principal: Principal, scenario: str, reading: str) -> dict:
    from aadesh_core.resolver import resolve_obligations
    from aadesh_adapters.corpus.s3 import S3Corpus

    authz = _authz_service()
    corpus = _corpus()

    # Authorize view
    authz.require_view_site_execution(principal=principal, site_id=SITE_ID, now=_now())

    result = resolve_obligations(
        site=_sites_store().get(SITE_ID),
        corpus=corpus,
        now=_now(),
        replay=None if scenario == "current" else _replay_context(),
        reading=_reading(reading),
    )

    return _json_response(200, _supervisor_payload(result, authz))


def _roster_get() -> dict:
    store = _parchi_store()
    parchis = store.for_site(SITE_ID)

    acknowledged = sum(1 for p in parchis if p.state.value in ("acknowledged", "sealed"))
    return _json_response(200, {
        "affected": WORKER_COUNT,
        "documented": len(parchis),
        "acknowledged": acknowledged,
        "sealed": sum(1 for p in parchis if p.state.value == "sealed"),
        "readiness_ready": REGISTERED_WORKERS,
        "readiness_total": WORKER_COUNT,
        "standings": _worker_standings(store),
    })


def _roster_qr_get(scenario: str) -> dict:
    store = _parchi_store()
    token_store = _token_store()

    impact = _roster_get()["body"]

    workers = []
    for i in range(1, WORKER_COUNT + 1):
        worker_id = f"worker-{i:03d}"
        parchi = store.get(f"parchi:exec-demo-001:{worker_id}")
        workers.append({
            "worker_id": worker_id,
            "display_name": f"Worker {i:03d}",
            "registered": worker_id in {f"worker-{j:03d}" for j in range(1, REGISTERED_WORKERS + 1)},
            "parchi_id": parchi.parchi_id if parchi else None,
            "state": parchi.state.value if parchi else None,
        })

    return _json_response(200, {"workers": workers, "impact": impact})


def _facilitator_get() -> dict:
    authz = _authz_service()
    store = _parchi_store()

    worker_id = "worker-001"
    parchi = store.get(f"parchi:exec-demo-001:{worker_id}")
    if parchi is None:
        return _json_response(200, {"error": "No parchi exists. Create a Standing Order first."})

    facilitator = _principal_from_claims(None, "facilitator")
    now = _now()

    consent = grant_consent(
        context_id="consent-demo-001",
        parchi_id=parchi.parchi_id,
        worker_id=worker_id,
        facilitator_id=FACILITATOR_ID,
        granted_at=now,
        ttl=None,  # Use default
        actor_worker_id=worker_id,
    )

    try:
        authz.require_assist_claim(principal=facilitator, consent=consent, now=now)
        view = describe_pending_parchi(consent=consent, parchi=parchi, facilitator_id=FACILITATOR_ID, now=now)
        assistance = {
            "attempted": ASSIST_CLAIM,
            "allowed": True,
            "policy_id": "permit-assist-with-consent",
            "reason": "Worker granted consent for this facilitator",
            "view": {
                "context_id": view.context_id,
                "parchi_id": view.parchi_id,
                "worker_id": view.worker_id,
                "site_id": view.site_id,
                "claim_status": view.claim_status,
                "consent_status": view.consent_status,
                "consent_granted_at": view.consent_granted_at.isoformat() if view.consent_granted_at else None,
                "consent_expires_at": view.consent_expires_at.isoformat() if view.consent_expires_at else None,
            },
        }
    except Exception as e:
        assistance = {
            "attempted": ASSIST_CLAIM,
            "allowed": False,
            "reason": str(e),
        }

    # ViewParchi denial for facilitator
    try:
        authz.require_view_parchi(principal=facilitator, parchi=parchi, now=now)
        read_attempt = {"attempted": VIEW_PARCHI, "allowed": True}
    except Exception as e:
        read_attempt = {"attempted": VIEW_PARCHI, "allowed": False, "reason": str(e)}

    return _json_response(200, {
        "worker_id": worker_id,
        "parchi_id": parchi.parchi_id,
        "assistance": assistance,
        "read_attempt": read_attempt,
    })


def _verify_get() -> dict:
    from aadesh_core.verification import verify

    corpus_root = Path("/var/task/corpus") if Path("/var/task/corpus").exists() else Path(__file__).parent.parent / "corpus"
    report = verify(corpus_root)

    return _json_response(200, {
        "sources": report.sources_checked,
        "citations": report.citations_checked,
        "passed": report.passed,
        "failures": [f.as_dict() for f in report.failures],
    })


def _impact_get() -> dict:
    store = _parchi_store()
    parchis = store.for_site(SITE_ID)

    # Get invocation info
    reading = _reading("aligned")
    stage = 3  # Demo: Stage III replay
    invoked_at = "2026-01-16T00:00:00Z"
    revoked_at = "2026-01-22T00:00:00Z"

    return _json_response(200, {
        "mode": "REPLAY",
        "is_replay": True,
        "is_current_invocation": False,
        "invocation": {
            "stage": stage,
            "invoked_at": invoked_at,
            "revoked_at": revoked_at,
            "order_doc_id": "caqm-grap-2026-01",
            "order_sha256": "demo-hash",
            "lifecycle": "revoked",
            "is_current": False,
        },
        "reading": {
            "station_id": reading.station_id if reading else "",
            "parameter": reading.parameter if reading else "",
            "value": reading.value if reading else 0,
            "observed_at": reading.observed_at.isoformat() if reading else None,
            "provenance": reading.provenance.value if reading else "synthetic",
            "is_synthetic": True,
            "is_measured": False,
            "is_replay": False,
        },
        "metrics": {
            "sites_with_active_standing_orders": {
                "count": 1,
                "label": "Sites with active Standing Orders",
                "description": "Sites with a signed Standing Order in effect",
                "status": "demo",
                "status_reason": "Demonstration value — one site in demo mode",
            },
            "sites_acknowledging_regulated_halts": {
                "count": 1,
                "label": "Sites acknowledging regulated halts",
                "description": "Sites where dust-generating activities are restricted",
                "status": "demo",
                "status_reason": "Demonstration value — Stage III replay active",
            },
            "dust_activities_halted": {
                "count": 3,
                "label": "Dust activities halted",
                "description": "Number of dust-generating activities restricted",
                "status": "demo",
                "status_reason": "Demonstration value",
            },
            "workers_with_documented_displacement": {
                "count": len(parchis),
                "label": "Workers with documented displacement",
                "description": "Workers issued a Parchi",
                "status": "demo",
                "status_reason": "Demonstration roster",
            },
        },
        "data_note": "Demo data — not production measurements",
        "claim_boundary": "Aadesh records compliance actions, not environmental outcomes",
    })


def _parchi_get(principal: Principal, parchi_id: str) -> dict:
    store = _parchi_store()
    parchi = store.get(parchi_id)
    if parchi is None:
        return _error_response(404, "Parchi not found")

    authz = _authz_service()
    try:
        authz.require_view_parchi(principal=principal, parchi=parchi, now=_now())
    except Exception as e:
        return _error_response(403, str(e))

    return _json_response(200, {
        "parchi_id": parchi.parchi_id,
        "site_id": parchi.site_id,
        "worker_id": parchi.worker_id,
        "state": parchi.state.value,
        "stage": parchi.stage.stage if parchi.stage else None,
        "issued_at": parchi.issued_at.isoformat() if parchi.issued_at else None,
        "acknowledged_at": parchi.acknowledged_at.isoformat() if parchi.acknowledged_at else None,
        "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
        "content_hash": parchi.content_hash,
        "obligation_ids": list(parchi.obligation_ids),
        "source_document_ids": list(parchi.source_document_ids),
    })


# ---------------------------------------------------------------------------
# POST handlers
# ---------------------------------------------------------------------------


def _standing_order_post(principal: Principal, scenario: str) -> dict:
    authz = _authz_service()
    store = _parchi_store()
    token_store = _token_store()
    ledger = _ledger()

    # Authorize halt issuance
    authz.require_issue_halt(principal=principal, site_id=SITE_ID, now=_now())

    # Create Standing Order
    order = create(
        site_id=SITE_ID,
        supervisor_id=SUPERVISOR_ID,
        trigger_stage=3,
        trigger_match="exact",
        valid_from=_now(),
        valid_until=_now().replace(day=_now().day + 7),
    )
    order = confirm(order, supervisor_id=SUPERVISOR_ID, now=_now())
    order = activate(order, now=_now())

    # Persist
    _standing_orders_store().save(order)

    # Create Parchis for roster
    roster = Roster(
        site_id=SITE_ID,
        entries=tuple(
            RosterEntry(worker_id=f"worker-{i:03d}", display_name=f"Worker {i:03d}")
            for i in range(1, WORKER_COUNT + 1)
        ),
    )

    execution = {
        "execution_id": f"exec-{order.standing_order_id}",
        "site_id": SITE_ID,
    }

    create_parchis_for_roster(
        execution=execution,
        roster=roster,
        provenance=_provenance(),
        idempotency_key=order.standing_order_id,
        store=store,
        tokens=token_store,
        ledger=ledger,
    )

    return _json_response(200, {
        "standing_order": {
            "standing_order_id": order.standing_order_id,
            "site_id": order.site_id,
            "supervisor_id": order.supervisor_id,
            "trigger": order.trigger.as_dict(),
            "actions": [a.as_dict() for a in order.actions],
            "valid_from": order.valid_from.isoformat(),
            "valid_until": order.valid_until.isoformat(),
            "status": order.status.value,
        },
        "impact": _roster_get()["body"],
    })


def _worker_view_post(payload: str) -> dict:
    store = _parchi_store()
    token_store = _token_store()

    try:
        view = describe_pending_parchi(payload=payload, now=_now(), store=store, tokens=token_store)
        return _json_response(200, {
            "status": "PENDING",
            "parchi_id": view.parchi_id,
            "site_id": view.site_id,
            "site_label": SITE_LABEL,
            "worker_id": view.worker_id,
            "state": view.state.value,
            "stage": view.stage,
            "provenance": view.provenance.value if view.provenance else None,
            "cites_measured_data": view.cites_measured_data,
            "obligation_ids": list(view.obligation_ids),
            "citations": _worker_citations(view.obligation_ids),
            "entitlement_refs": list(view.entitlement_refs),
            "readiness_checklist": list(view.readiness_checklist),
            "displaced_worker_days": view.displaced_worker_days,
            "source_document_ids": list(view.source_document_ids),
            "source_hashes": list(view.source_hashes),
            "expires_at": view.expires_at.isoformat(),
        })
    except Exception:
        parchi = resolve_parchi_for_payload(payload=payload, now=_now(), store=store, tokens=token_store)
        return _json_response(200, {
            "status": "ACKNOWLEDGED" if parchi.acknowledged_at else parchi.state.value.upper(),
            "parchi_id": parchi.parchi_id,
            "site_id": parchi.site_id,
            "site_label": SITE_LABEL,
            "worker_id": parchi.worker_id,
            "state": parchi.state.value,
            "stage": parchi.stage.stage if parchi.stage else None,
            "citations": _worker_citations(parchi.obligation_ids),
            "acknowledged_at": parchi.acknowledged_at.isoformat() if parchi.acknowledged_at else None,
            "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
            "content_hash": parchi.content_hash,
        })


def _worker_acknowledge_post(
    principal: Principal,
    payload: str,
    worker_id: str,
) -> dict:
    authz = _authz_service()
    store = _parchi_store()
    token_store = _token_store()
    ledger = _ledger()

    # Authorize and acknowledge in one step — the gate pattern
    outcome = authz.acknowledge_own_parchi(
        principal=principal,
        payload=payload,
        now=_now(),
        store=store,
        tokens=token_store,
        ledger=ledger,
    )

    return _json_response(200, {
        "parchi": {
            "parchi_id": outcome.parchi.parchi_id,
            "site_id": outcome.parchi.site_id,
            "worker_id": outcome.parchi.worker_id,
            "state": outcome.parchi.state.value,
            "acknowledged_at": outcome.parchi.acknowledged_at.isoformat() if outcome.parchi.acknowledged_at else None,
            "sealed_at": outcome.parchi.sealed_at.isoformat() if outcome.parchi.sealed_at else None,
        },
        "already_confirmed": outcome.already_confirmed,
        "event_id": outcome.event.event_id,
    })


def _cedar_supervisor_acknowledge(principal: Principal, worker_id: str) -> dict:
    """Demonstrate Cedar denial — supervisor cannot acknowledge worker's parchi."""
    store = _parchi_store()
    token_store = _token_store()

    payload = token_store.get(f"worker-{worker_id}")
    if payload is None:
        return _json_response(200, {
            "attempted": "AcknowledgeOwnParchi",
            "denied": True,
            "allowed": False,
            "reason": f"No acknowledgement link for worker {worker_id}",
            "policy_id": None,
        })

    try:
        _authz_service().acknowledge_own_parchi(
            principal=principal,
            payload=payload,
            now=_now(),
            store=store,
            tokens=token_store,
            ledger=_ledger(),
        )
        return _json_response(200, {
            "attempted": "AcknowledgeOwnParchi",
            "denied": False,
            "allowed": True,
        })
    except Exception as e:
        return _json_response(200, {
            "attempted": "AcknowledgeOwnParchi",
            "denied": True,
            "allowed": False,
            "reason": str(e),
            "policy_id": "no-proxy-acknowledgement",
        })


def _assist_post(
    principal: Principal,
    worker_id: str,
    parchi_id: str,
) -> dict:
    authz = _authz_service()
    store = _parchi_store()

    parchi = store.get(parchi_id)
    if parchi is None:
        return _error_response(404, "Parchi not found")

    now = _now()
    consent = grant_consent(
        context_id=f"consent-{parchi_id}",
        parchi_id=parchi_id,
        worker_id=worker_id,
        facilitator_id=principal.principal_id,
        granted_at=now,
        ttl=None,
        actor_worker_id=worker_id,
    )

    try:
        authz.require_assist_claim(principal=principal, consent=consent, now=now)
        view = describe_pending_parchi(consent=consent, parchi=parchi, facilitator_id=principal.principal_id, now=now)

        return _json_response(200, {
            "allowed": True,
            "view": {
                "context_id": view.context_id,
                "parchi_id": view.parchi_id,
                "worker_id": view.worker_id,
                "site_id": view.site_id,
                "claim_status": view.claim_status,
                "consent_status": view.consent_status,
                "consent_granted_at": view.consent_granted_at.isoformat() if view.consent_granted_at else None,
                "consent_expires_at": view.consent_expires_at.isoformat() if view.consent_expires_at else None,
                # Redacted — no PII
            },
        })
    except Exception as e:
        return _json_response(200, {
            "allowed": False,
            "reason": str(e),
        })


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _replay_context():
    from aadesh_core.domain import ReplayContext
    return ReplayContext(
        invocation_date="2026-01-16",
        revocation_date="2026-01-22",
    )


def _reading(key: str):
    from aadesh_core.domain import StationReading, Provenance
    from datetime import datetime

    if key == "aligned":
        return StationReading(
            station_id="DL-NCR-ROHINI-01",
            parameter="PM2.5",
            value=285.0,
            observed_at=datetime(2026, 1, 16, 8, 0, 0),
            ingested_at=datetime(2026, 1, 16, 8, 5, 0),
            provenance=Provenance.SYNTHETIC,
        )
    elif key == "divergent":
        return StationReading(
            station_id="DL-NCR-ROHINI-01",
            parameter="PM2.5",
            value=180.0,
            observed_at=datetime(2026, 1, 16, 8, 0, 0),
            ingested_at=datetime(2026, 1, 16, 8, 5, 0),
            provenance=Provenance.SYNTHETIC,
        )
    return None


def _provenance():
    from aadesh_core.parchi_ack import ParchiProvenance
    from aadesh_core.domain import InvokedStage

    return ParchiProvenance(
        stage=InvokedStage(
            stage=3,
            invoked_at=datetime(2026, 1, 16, 0, 0, 0),
            lifecycle="active",
            order_doc_id="caqm-grap-2026-01",
            order_sha256="demo-hash",
        ),
        reading=_reading("aligned"),
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


def _worker_citations(obligation_ids: list[str]) -> list[dict]:
    """Return citations from corpus for given obligation IDs."""
    corpus = _corpus()
    citations = []

    for obl_id in obligation_ids:
        obligations = corpus.obligations()
        for obl in obligations:
            if obl.obligation_id == obl_id and obl.source_state.value == "verified":
                doc = corpus.document(obl.source_doc)
                if doc and doc.sha256 == obl.source_hash:
                    citations.append({
                        "obligation_id": obl.obligation_id,
                        "source_doc": obl.source_doc,
                        "source_title": doc.title,
                        "source_page": obl.source_page,
                        "source_quote": obl.source_quote,
                        "source_hash": obl.source_hash,
                        "source_url": doc.source_url,
                    })
    return citations


def _worker_standings(store) -> list[dict]:
    roster_entries = [
        {"worker_id": f"worker-{i:03d}", "display_name": f"Worker {i:03d}"}
        for i in range(1, WORKER_COUNT + 1)
    ]

    parchis_by_worker = {p.worker_id: p for p in store.for_site(SITE_ID)}

    standings = []
    for entry in roster_entries:
        parchi = parchis_by_worker.get(entry["worker_id"])
        standings.append({
            "worker_id": entry["worker_id"],
            "display_name": entry["display_name"],
            "registered": entry["worker_id"] in {f"worker-{j:03d}" for j in range(1, REGISTERED_WORKERS + 1)},
            "parchi_id": parchi.parchi_id if parchi else None,
            "state": parchi.state.value if parchi else None,
            "has_qr": parchi is not None,
        })
    return standings


def _supervisor_payload(result, authz) -> dict:
    """Build supervisor screen payload from resolution result."""
    from aadesh_core.resolver import resolution_to_dict

    payload = resolution_to_dict(result)

    # Add site info
    payload["site"] = {
        "site_id": SITE_ID,
        "label": SITE_LABEL,
        "activity_type": "Piling works",
        "project_category": "Infrastructure",
    }

    # Add stage detail
    payload["stage_detail"] = {
        "official_stage": result.stage.stage if result.stage else "NONE",
        "is_replay": result.mode.value == "REPLAY",
        "lifecycle": result.stage.lifecycle.value if result.stage else None,
        "order_doc_id": result.stage.order_doc_id if result.stage else None,
        "order_date": result.stage.invoked_at.isoformat() if result.stage else None,
        "order_short_hash": (result.stage.order_sha256 or "")[:8] if result.stage else None,
        "revoked_at": result.stage.revoked_at.isoformat() if result.stage and result.stage.revoked_at else None,
        "discrepancy": result.stage_status.status.value == "DISCREPANCY",
    }

    # Add standing order if exists
    sord = _standing_orders_store().get(SITE_ID)
    if sord:
        payload["standing_order"] = {
            "standing_order_id": sord.standing_order_id,
            "site_id": sord.site_id,
            "supervisor_id": sord.supervisor_id,
            "trigger": sord.trigger.as_dict(),
            "actions": [a.as_dict() for a in sord.actions],
            "valid_from": sord.valid_from.isoformat(),
            "valid_until": sord.valid_until.isoformat(),
            "status": sord.status.value,
            "projected_status": sord.projected_status().value,
        }

    # Add reading info
    if result.reading:
        from datetime import datetime, timedelta
        age = datetime.now(UTC) - result.reading.observed_at
        payload["reading"]["age_minutes"] = int(age.total_seconds() // 60)
        payload["reading"]["freshness"] = "FRESH" if age <= timedelta(minutes=90) else "STALE"

    payload["impact"] = _roster_get()["body"]

    return payload
