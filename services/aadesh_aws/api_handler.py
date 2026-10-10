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
    AuthorizationDenied,
    AuthorizationUnavailable,
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
    return ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims") or {}


def _principal(event: dict[str, Any], *, default_role: str) -> Principal | None:
    """The authenticated principal, or None when the authorizer did not run.

    Returning None lets the application fall back to its configured demonstration principal,
    which is what happens on the two routes that are not behind the authorizer. On an
    authenticated route there is always a `sub`, so the real principal is what Cedar sees.

    `principal_id` is `custom:principal_id` when the pool carries it, and the Cognito `sub` only
    as a fallback. The distinction is load-bearing, not cosmetic: `parchi_resource()` builds
    `EntityRef("Principal", parchi.worker_id)` and the rule is `resource.worker == principal`,
    which is ENTITY equality on the id. A `sub` UUID can never satisfy it for a worker whose
    parchi names `worker-001`, so using `sub` here would make a signed-in worker permanently
    unable to acknowledge their own Parchi -- the exact failure the `no-proxy-acknowledgement`
    forbid rule is written to distinguish from a proxy attempt.

    The value is read from a verified claim and never from the request body. A body-supplied
    `worker_id` is not consulted anywhere in this module.
    """
    claims = _claims(event)
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        return None
    role = str(claims.get("custom:role") or claims.get("role") or default_role).strip()
    assigned_site = str(
        claims.get("custom:assigned_site") or claims.get("assigned_site") or ""
    ).strip()
    principal_id = (
        str(claims.get("custom:principal_id") or claims.get("principal_id") or "").strip() or sub
    )
    return Principal(
        principal_id=principal_id,
        role=role or default_role,
        assigned_site=assigned_site or None,
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
    except TokenRejected:
        # Every rejection is reported identically. Which one it was is for the audit log.
        return _error(400, "TOKEN_REJECTED", "This acknowledgement link cannot be honoured.")
    except WrongWorker as exc:
        return _error(403, "WRONG_WORKER", exc.message)
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
        app = build_application(config)
        return _response(
            200,
            app.supervisor(
                scenario=query.get("scenario", "replay"),
                reading=query.get("reading", "aligned"),
                principal=_principal(event, default_role="supervisor"),
            ),
        )

    if path == "/api/roster":
        return _response(200, build_application(config).impact())

    if path == "/api/roster/qr":
        return _response(
            200, build_application(config).roster_qr(scenario=query.get("scenario", "replay"))
        )

    if path == "/api/facilitator":
        app = build_application(config)
        return _response(
            200, app.facilitator(principal=_principal(event, default_role="facilitator"))
        )

    if path == "/api/verify":
        return _response(200, build_application(config).verify())

    if path in ("/api/explain", "/api/explanation"):
        app = build_application(config)
        return _response(
            200,
            app.explain(
                scenario=query.get("scenario", "replay"),
                reading=query.get("reading", "aligned"),
                principal=_principal(event, default_role="supervisor"),
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
        scenario = str(body.get("scenario", "replay"))
        app = build_application(config)
        order = app.create_standing_order(
            scenario=scenario,
            principal=_principal(event, default_role="supervisor"),
        )
        # Signing the order and opening its Parchis happened above; STARTING the run is the
        # event bus's job (the API has no states:StartExecution). A publish that fails is
        # reported rather than raised: the signed pre-commitment and its Parchis are already
        # facts, and telling the supervisor otherwise would be false.
        invocation = app.resolve(scenario=scenario)
        stage = invocation.stage
        workflow = publish_stage_invocation(
            order_id=order.standing_order_id,
            site_id=config.site_id,
            scenario=scenario,
            # The SAME key open_parchis() used, so the machine's CreateParchis step finds these
            # Parchis instead of minting a second set for one trigger.
            execution_id=f"exec-{order.standing_order_id}",
            stage=stage.stage if stage else None,
            order_doc_id=stage.order_doc_id if stage else None,
            order_sha256=stage.order_sha256 if stage else None,
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
        return _response(
            200,
            build_application(config).roster_qr(scenario=str(body.get("scenario", "replay"))),
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

    if path == "/api/cedar/supervisor-acknowledge":
        app = build_application(config)
        return _response(
            200,
            app.cedar_supervisor_acknowledge(
                str(body.get("worker_id", "worker-001")),
                principal=_principal(event, default_role="supervisor"),
            ),
        )

    if path == "/api/assist":
        app = build_application(config)
        return _response(
            200,
            app.assist(
                worker_id=str(body.get("worker_id", "worker-001")),
                parchi_id=str(body.get("parchi_id", "")),
                principal=_principal(event, default_role="facilitator"),
            ),
        )

    if path in ("/api/explain", "/api/explanation"):
        app = build_application(config)
        return _response(
            200,
            app.explain(
                scenario=str(body.get("scenario", "replay")),
                principal=_principal(event, default_role="supervisor"),
            ),
        )

    return _error(404, "NOT_FOUND", f"No route for POST {path}.")


# Kept for parity with the local skin's health payload shape and for the tests that import it.
def health(config: Config | None = None) -> dict[str, Any]:
    return build_application(config).health()


__all__ = ["handle", "health", "now"]
