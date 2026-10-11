"""API Gateway handler -- the HTTP skin the deployed frontend talks to.

This is a translation layer and nothing else: it reads a request, builds a `Principal` from the
Cognito claims the authorizer already verified, calls `AadeshApplication`, and serialises the
reply. Every decision -- the stage, the obligations, the Cedar decision, the parchi state --
comes from `aadesh_core` via the application, exactly as it does locally.

Two routes are deliberately NOT behind the Cognito authorizer, and both are protected by
something stronger than a session:

  * `/api/worker/view` and `/api/worker/acknowledge` are protected by the opaque
    acknowledgement token in the payload itself. That token is a 256-bit bearer credential
    that names one parchi and one worker; requiring a login as well would mean a worker needed
    an account to read a slip handed to them on site, and would add nothing -- the sidebar
    says the same thing in `web/app/worker/page.tsx`.
  * `/api/impact` and `/api/health` are public because they are aggregate-only by construction
    (the public impact payload is asserted, in the core's own tests, to contain no worker id,
    name, or token) and because an uptime check should not need a user.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aadesh_aws.events import publish_stage_invocation
from aadesh_aws.runtime import Config, build_application, now
from aadesh_core.domain import Principal
from aadesh_core.errors import (
    AadeshError,
    AuthenticatedPrincipalRequired,
    AuthorizationDenied,
    AuthorizationUnavailable,
    ConsentRefused,
    ConsentStoreConflict,
    OperationalWriteDenied,
    RosterSiteUnavailable,
    TokenRejected,
    WrongWorker,
)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("AADESH_ALLOWED_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _response(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8", **CORS_HEADERS},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _error(status: int, code: str, reason: str, **extra: Any) -> dict[str, Any]:
    return _response(status, {"error": code, "reason": reason, **extra})


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _query(event: dict[str, Any]) -> dict[str, str]:
    return {k: v for k, v in (event.get("queryStringParameters") or {}).items() if v is not None}


def _claims(event: dict[str, Any]) -> dict[str, Any]:
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims")
    return claims if isinstance(claims, dict) else {}


class PrincipalClaimError(Exception):
    """Verified Cognito identity is missing a valid administrator-provisioned role profile."""


VALID_ROLES = frozenset({"supervisor", "facilitator", "worker"})


def _principal(event: dict[str, Any]) -> Principal:
    """Build a principal only from verified, provisioned Cognito claims; never invent a role."""
    claims = _claims(event)
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip() or sub != sub.strip():
        raise PrincipalClaimError()
    role_claim = claims.get("custom:role")
    if not isinstance(role_claim, str) or role_claim not in VALID_ROLES:
        raise PrincipalClaimError()
    role = role_claim
    site_claim = claims.get("custom:assigned_site")
    if site_claim is not None and (
        not isinstance(site_claim, str)
        or not site_claim.strip()
        or site_claim != site_claim.strip()
    ):
        raise PrincipalClaimError()
    assigned_site = site_claim.strip() if isinstance(site_claim, str) else None
    if role == "supervisor" and assigned_site is None:
        raise PrincipalClaimError()
    principal_claim = claims.get("custom:principal_id")
    if principal_claim is not None and (
        not isinstance(principal_claim, str)
        or not principal_claim.strip()
        or principal_claim != principal_claim.strip()
    ):
        raise PrincipalClaimError()
    principal_id = principal_claim.strip() if isinstance(principal_claim, str) else sub.strip()
    return Principal(
        principal_id=principal_id,
        role=role,
        assigned_site=assigned_site,
    )


def handle(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    method = (event.get("httpMethod") or "GET").upper()
    path = event.get("path") or "/"

    if method == "OPTIONS":
        return _response(204, {})

    try:
        if method == "GET":
            return _get(path, event)
        if method == "POST":
            return _post(path, event)
        return _error(405, "METHOD_NOT_ALLOWED", f"{method} is not supported on {path}.")
    except AuthorizationDenied as exc:
        return _error(
            403,
            "AUTHORIZATION_DENIED",
            getattr(exc.decision, "reason", str(exc)),
            policy_id=getattr(exc.decision, "policy_id", None),
        )
    except AuthorizationUnavailable as exc:
        # Fail closed, and say which failure it is: an outage is not a denial.
        return _error(503, "AUTHORIZATION_UNAVAILABLE", str(exc))
    except ConsentStoreConflict:
        # A stale write lost its race against a newer consent decision. Retrying with fresh
        # state is safe; applying the stale write is not. Nothing was written.
        return _error(
            409,
            "CONSENT_CONFLICT",
            "The consent changed while this request was being processed. Please try again.",
        )
    except ConsentRefused as exc:
        # The message is a fixed, safe sentence chosen per case -- never a lookup result.
        return _error(403, "CONSENT_REFUSED", str(exc))
    except TokenRejected:
        # Every rejection is reported identically. Which one it was is for the audit log.
        return _error(400, "TOKEN_REJECTED", "This acknowledgement link cannot be honoured.")
    except WrongWorker as exc:
        return _error(403, "WRONG_WORKER", exc.message)
    except PrincipalClaimError:
        return _error(403, "INVALID_PRINCIPAL", "A provisioned role and identity are required.")
    except AuthenticatedPrincipalRequired:
        return _error(403, "INVALID_PRINCIPAL", "A provisioned role and identity are required.")
    except OperationalWriteDenied as exc:
        return _error(403, "OPERATIONAL_WRITE_DENIED", str(exc))
    except RosterSiteUnavailable as exc:
        return _error(403, "ROSTER_ACCESS_DENIED", str(exc))
    except AadeshError as exc:
        return _error(400, type(exc).__name__, str(exc))
    except Exception as exc:
        return _error(500, "INTERNAL", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


def _get(path: str, event: dict[str, Any]) -> dict[str, Any]:
    query = _query(event)
    config = Config.from_env()

    if path == "/api/health":
        return _response(
            200, {**build_application(config).health(), "environment": config.environment}
        )

    if path == "/api/impact":
        return _response(200, build_application(config).public_impact())

    if path == "/api/reading/latest":
        return _response(200, build_application(config).latest_reading())

    if path == "/api/supervisor":
        principal = _principal(event)
        app = build_application(config)
        return _response(
            200,
            app.supervisor(
                scenario=query.get("scenario", "replay"),
                reading=query.get("reading", "aligned"),
                principal=principal,
            ),
        )

    if path == "/api/roster":
        principal = _principal(event)
        app = build_application(config)
        app.authorize_roster_access(principal=principal, site_id=query.get("site_id"))
        return _response(200, app.impact())

    if path == "/api/roster/qr":
        principal = _principal(event)
        return _response(
            200,
            build_application(config).roster_qr(
                scenario=query.get("scenario", "current"),
                principal=principal,
                site_id=query.get("site_id"),
            ),
        )

    if path == "/api/facilitator":
        principal = _principal(event)
        app = build_application(config)
        return _response(200, app.facilitator(principal=principal))

    if path == "/api/verify":
        _principal(event)
        return _response(200, build_application(config).verify())

    if path in ("/api/explain", "/api/explanation"):
        principal = _principal(event)
        app = build_application(config)
        return _response(
            200,
            app.explain(
                scenario=query.get("scenario", "replay"),
                reading=query.get("reading", "aligned"),
                principal=principal,
            ),
        )

    return _error(404, "NOT_FOUND", f"No route for GET {path}.")


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------


def _post(path: str, event: dict[str, Any]) -> dict[str, Any]:
    body = _body(event)
    config = Config.from_env()

    if path == "/api/standing-order":
        scenario = str(body.get("scenario", "current"))
        principal = _principal(event)
        app = build_application(config)
        order = app.create_standing_order(
            scenario=scenario,
            principal=principal,
        )
        # Signing the order and opening its Parchis happened above; STARTING the run is the
        # event bus's job (the API has no states:StartExecution). A publish that fails is
        # reported rather than raised: the signed pre-commitment and its Parchis are already
        # facts, and telling the supervisor otherwise would be false.
        invocation = app.operational_invocation
        workflow = publish_stage_invocation(
            order_id=order.standing_order_id,
            site_id=config.site_id,
            scenario="current",
            # The SAME key open_parchis() used, so the machine's CreateParchis step finds these
            # Parchis instead of minting a second set for one trigger.
            execution_id=f"exec-{order.standing_order_id}",
            stage=invocation.stage if invocation else None,
            order_doc_id=invocation.order_doc_id if invocation else None,
            order_sha256=invocation.order_sha256 if invocation else None,
            bus_name=config.event_bus_name,
        )
        return _response(
            200,
            {
                "standing_order": app.standing_order_payload(),
                "impact": app.impact(),
                "workflow": workflow,
            },
        )

    if path == "/api/roster/qr":
        principal = _principal(event)
        return _response(
            200,
            build_application(config).roster_qr(
                scenario=str(body.get("scenario", "current")),
                principal=principal,
                site_id=str(body.get("site_id") or "") or None,
            ),
        )

    if path == "/api/worker/view":
        return _response(200, build_application(config).worker_view(str(body.get("payload", ""))))

    if path == "/api/worker/acknowledge":
        return _response(
            200,
            build_application(config).acknowledge(
                str(body.get("payload", "")), str(body.get("worker_id", ""))
            ),
        )

    if path == "/api/consent/grant":
        principal = _principal(event)
        # The actor is the verified principal, never the body. Only a provisioned worker may
        # grant consent, and only for a Parchi their own identity owns -- both re-checked by
        # the application against the Parchi's stored worker. A facilitator or supervisor
        # cannot grant on the worker's behalf.
        if principal.role != "worker":
            return _error(
                403,
                "AUTHORIZATION_DENIED",
                "Only the worker named on the Parchi may grant consent for their own claim.",
            )
        app = build_application(config)
        return _response(
            200,
            app.grant_consent(
                parchi_id=str(body.get("parchi_id", "")),
                worker_id=str(body.get("worker_id", "")),
                facilitator_id=str(body.get("facilitator_id") or "") or None,
                actor_worker_id=principal.principal_id,
            ),
        )

    if path == "/api/consent/revoke":
        principal = _principal(event)
        # There is no other, explicitly authorized revocation mechanism in this codebase, so
        # only the worker themselves may revoke. The application verifies the principal is the
        # worker named on the consent, not merely that they are signed in.
        if principal.role != "worker":
            return _error(
                403,
                "AUTHORIZATION_DENIED",
                "Only the worker named on the consent may revoke it.",
            )
        app = build_application(config)
        return _response(
            200,
            app.revoke_consent(
                context_id=str(body.get("context_id", "")),
                actor_worker_id=principal.principal_id,
            ),
        )

    if path == "/api/cedar/supervisor-acknowledge":
        principal = _principal(event)
        app = build_application(config)
        return _response(
            200,
            app.cedar_supervisor_acknowledge(
                str(body.get("worker_id", "worker-001")),
                principal=principal,
            ),
        )

    if path == "/api/assist":
        principal = _principal(event)
        app = build_application(config)
        return _response(
            200,
            app.assist(
                worker_id=str(body.get("worker_id", "worker-001")),
                parchi_id=str(body.get("parchi_id", "")),
                principal=principal,
            ),
        )

    if path in ("/api/explain", "/api/explanation"):
        principal = _principal(event)
        app = build_application(config)
        return _response(
            200,
            app.explain(
                scenario=str(body.get("scenario", "replay")),
                principal=principal,
            ),
        )

    return _error(404, "NOT_FOUND", f"No route for POST {path}.")


# Kept for parity with the local skin's health payload shape and for the tests that import it.
def health(config: Config | None = None) -> dict[str, Any]:
    return build_application(config).health()


__all__ = ["handle", "health", "now"]
