"""The Aadesh local web API: a thin `http.server` skin over `AadeshApplication`.

This is the "local HTTP server" the architecture doc promised -- the same application that sits
behind the Lambda handler, exposed to the Next.js frontend as JSON. It adds no rules of its own:

  * the stage, the obligations and their citations come from `resolve_obligations` over a
    verification snapshot of `corpus/`;
  * every refusal (a supervisor acknowledging a worker's parchi, a facilitator reading a
    record) comes from the REAL Cedar engine, evaluated from `infra/cedar/policies.cedar`;
  * `verification` runs `run_verify` in-process, so the screen shows the actual exit code
    rather than a claim about it.

Since the AWS deployment landed, the behaviour itself lives in `aadesh_app.application`. This
module's only jobs are to wire the in-memory adapters and the local corpus together, and to
translate HTTP requests into calls on that application. The AWS Lambda handler wires the
DynamoDB/S3 adapters into the SAME application, which is what makes "the same logic runs
locally and on AWS" a fact rather than a promise.

State is in-memory and lives for the life of the process. This is a local demonstration
adapter: there is no database, no session, and no persistence, by design.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_adapters.store.memory_standing_order import InMemoryStandingOrderStore
from aadesh_adapters.store.memory_task_token import InMemoryTaskTokenStore
from aadesh_app.application import AadeshApplication
from aadesh_cli.verify import run_verify
from aadesh_core.domain import ConstructionSite
from aadesh_core.errors import AadeshError
from aadesh_core.parchi_ack import Roster, RosterEntry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = PROJECT_ROOT / "corpus"
CEDAR_DIR = PROJECT_ROOT / "infra" / "cedar"

SITE_ID = "example-piling-site"
SITE_LABEL = "Construction Site — Delhi-NCR"
SITE_FIXTURE = PROJECT_ROOT / "fixtures" / "sites" / "piling-site.json"
SUPERVISOR_ID = "supervisor-001"
FACILITATOR_ID = "facilitator-001"

# The demonstration roster. Site data, not legal corpus data: worker count is not an
# entitlement multiplier, and `registered` is documentation readiness only -- it is NOT a
# claim that anyone is entitled to any sum.
WORKER_COUNT = 34
REGISTERED_WORKERS = 27


class Demo(AadeshApplication):
    """In-memory demonstration state over the real deterministic core."""

    def __init__(self, corpus_root: Path = DEFAULT_CORPUS) -> None:
        corpus_root = Path(corpus_root)
        site = ConstructionSite.from_dict(json.loads(SITE_FIXTURE.read_text(encoding="utf-8")))
        super().__init__(
            site=site,
            roster=Roster(
                site_id=SITE_ID,
                entries=tuple(
                    RosterEntry(worker_id=f"worker-{i:03d}", display_name=f"Worker {i:03d}")
                    for i in range(1, WORKER_COUNT + 1)
                ),
            ),
            registered={f"worker-{i:03d}" for i in range(1, REGISTERED_WORKERS + 1)},
            store=InMemoryParchiStore(),
            tokens=InMemoryAcknowledgementTokenStore(),
            ledger=InMemoryIdempotencyLedger(),
            authz=CedarAuthorizationProvider(
                policy_path=CEDAR_DIR / "policies.cedar",
                denials_path=CEDAR_DIR / "denials.json",
                schema_path=CEDAR_DIR / "schema.cedarschema.json",
            ),
            corpus=lambda: LocalFileCorpus(corpus_root),
            audit=RecordingAuditLog(),
            site_id=SITE_ID,
            site_label=SITE_LABEL,
            supervisor_id=SUPERVISOR_ID,
            facilitator_id=FACILITATOR_ID,
            corpus_root=corpus_root,
            verify_runner=run_verify,
            order_store=InMemoryStandingOrderStore(),
            task_tokens=InMemoryTaskTokenStore(),
        )


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    demo: Demo  # set by serve()

    def log_message(self, *args: Any) -> None:
        return

    # -- helpers ------------------------------------------------------------

    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def do_OPTIONS(self) -> None:
        self._send(204, {})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            self._route_get(parsed.path, query)
        except (AadeshError, ValueError, KeyError) as exc:
            self._send(400, {"error": type(exc).__name__, "reason": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            self._route_post(parsed.path, self._read_body())
        except (AadeshError, ValueError, KeyError) as exc:
            self._send(400, {"error": type(exc).__name__, "reason": str(exc)})

    # -- routes -------------------------------------------------------------

    def _route_get(self, path: str, query: dict[str, str]) -> None:
        demo = self.demo
        if path == "/api/health":
            self._send(200, demo.health())
        elif path == "/api/supervisor":
            self._send(
                200,
                demo.supervisor(
                    scenario=query.get("scenario", "replay"),
                    reading=query.get("reading", "aligned"),
                ),
            )
        elif path == "/api/roster":
            self._send(200, demo.impact())
        elif path == "/api/roster/qr":
            self._send(200, demo.roster_qr(scenario=query.get("scenario", "replay")))
        elif path == "/api/facilitator":
            self._send(200, demo.facilitator())
        elif path == "/api/verify":
            self._send(200, demo.verify())
        elif path == "/api/impact":
            self._send(200, demo.public_impact())
        elif path == "/api/reading/latest":
            self._send(200, demo.latest_reading())
        elif path in ("/api/explain", "/api/explanation"):
            self._send(
                200,
                demo.explain(
                    scenario=query.get("scenario", "replay"),
                    reading=query.get("reading", "aligned"),
                ),
            )
        else:
            self._send(404, {"error": "NOT_FOUND", "path": path})

    def _route_post(self, path: str, body: dict[str, Any]) -> None:
        demo = self.demo
        if path == "/api/standing-order":
            order = demo.create_standing_order(scenario=body.get("scenario", "replay"))
            self._send(
                200,
                {
                    "standing_order": demo.standing_order_payload(),
                    "impact": demo.impact(),
                    "order_status": order.status.value,
                },
            )
        elif path == "/api/roster/qr":
            self._send(200, demo.roster_qr(scenario=body.get("scenario", "replay")))
        elif path == "/api/worker/view":
            self._send(200, demo.worker_view(str(body.get("payload", ""))))
        elif path == "/api/worker/acknowledge":
            self._send(
                200,
                demo.acknowledge(str(body.get("payload", "")), str(body.get("worker_id", ""))),
            )
        elif path == "/api/cedar/supervisor-acknowledge":
            self._send(
                200, demo.cedar_supervisor_acknowledge(str(body.get("worker_id", "worker-001")))
            )
        elif path == "/api/assist":
            self._send(
                200,
                demo.assist(
                    worker_id=str(body.get("worker_id", "worker-001")),
                    parchi_id=str(body.get("parchi_id", "")),
                ),
            )
        elif path in ("/api/explain", "/api/explanation"):
            self._send(200, demo.explain(scenario=body.get("scenario", "replay")))
        else:
            self._send(404, {"error": "NOT_FOUND", "path": path})


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    demo = Demo()
    handler = type("BoundHandler", (Handler,), {"demo": demo})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Aadesh API listening on http://{host}:{port}  (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aadesh-web", description="Aadesh local JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
