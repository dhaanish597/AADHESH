#!/usr/bin/env python
"""Execute the documented verification flows against a DEPLOYED stack, and record the evidence.

`make verify` proves the corpus offline. `make test` proves the core offline. This proves the
thing neither can: that the deployed URL, the deployed identity and the deployed workflow agree
with each other. It is the only check that can fail because of an IAM policy, a table name that
was never set on a function's environment, or a state machine whose paths only resolve at run
time.

It needs real credentials (`aws configure`) and reaches real AWS, so it is NOT on the default
test path and never will be.

    uv run --with boto3 python infra/aws/verify_deployment.py \
        --api-url https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod \
        --user-pool-id ap-south-1_xxxxxxx --client-id xxxxxxxxxxxxxxxxxxx

Every flow reports PASS, FAIL or SKIP with the observation that decided it, and the whole run is
written to JSON so the evidence can be kept. A failure is reported as a failure: nothing here
retries its way to green, and a flow that cannot be exercised is marked SKIP with the reason
rather than counted as a pass.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / ".deploy" / "verification.json"

DEMO_USERS = {
    "supervisor": "supervisor@aadesh.example",
    "facilitator": "facilitator@aadesh.example",
    "worker": "worker@aadesh.example",
}

#: The parchi view/ack calls are the ONLY ones that need no token: they are protected by the
#: opaque per-parchi token in the payload, which is what a worker scans on site.
PUBLIC_ROUTES = ("/api/health", "/api/impact", "/api/reading/latest")
PROTECTED_ROUTE = "/api/supervisor"


class Flow:
    """One recorded flow: what it proves, what was seen, and whether it passed.

    A flow that cannot be exercised is SKIPped with the reason, never counted as a pass. The
    deployed system holds real state, so some flows can only be exercised ONCE per corpus: a
    deterministic id cannot be re-minted, and an idempotent operation cannot be performed
    afresh. Reporting SKIP is the honest reading of that, and a failure still wins over it.
    """

    def __init__(self, number: int, name: str) -> None:
        self.number = number
        self.name = name
        self.observations: dict[str, Any] = {}
        self.failures: list[str] = []
        self.skips: list[str] = []

    def observe(self, **values: Any) -> None:
        self.observations.update(values)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(message)

    def skip(self, reason: str) -> None:
        self.skips.append(reason)

    @property
    def status(self) -> str:
        if self.failures:
            return "FAIL"
        return "SKIP" if self.skips else "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "flow": self.number,
            "name": self.name,
            "status": self.status,
            "failures": self.failures,
            "skipped": self.skips,
            "observations": self.observations,
        }


class Client:
    """A thin HTTP client. Uses only the stdlib so the script's own dependencies stay honest."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict[str, Any] | None = None,
        timeout: int = 180,
    ) -> tuple[int, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(f"{self.api_url}{path}", data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw
        except urllib.error.URLError as exc:  # pragma: no cover -- network failure
            return 0, {"error": str(exc)}

    def _send_headers(
        self, request: urllib.request.Request, timeout: int = 60
    ) -> tuple[int, dict[str, str]]:
        """Send a request and return its status with its response headers, lower-cased.

        Errors are the interesting case here, not an exception: a 401 is exactly what flow 1
        needs to read the headers of, and `HTTPError` still carries them.
        """
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}
        except urllib.error.URLError as exc:  # pragma: no cover -- network failure
            return 0, {"error": str(exc)}

    def preflight(self, path: str, *, origin: str, method: str = "GET"):
        """An `OPTIONS` preflight, shaped the way a browser sends one.

        Every other call in this file is made by a client that does not preflight, and that is the
        gap this method exists to close: an authenticated request from the console triggers a
        preflight first, and the browser refuses the whole call when
        `Access-Control-Allow-Origin` is not exactly the page's own origin. A curl-shaped
        verification can therefore pass completely while the console reports "Failed to fetch".
        """
        request = urllib.request.Request(f"{self.api_url}{path}", method="OPTIONS")
        request.add_header("Origin", origin)
        request.add_header("Access-Control-Request-Method", method)
        request.add_header("Access-Control-Request-Headers", "authorization")
        return self._send_headers(request)

    def headers_for(self, method: str, path: str, *, origin: str, token: str | None = None):
        """A real request whose response headers matter -- the refusal a browser has to be able to
        read. Without `Access-Control-Allow-Origin` on it, the browser reports a network fault and
        the console tells the user the API is down instead of asking them to sign in."""
        request = urllib.request.Request(f"{self.api_url}{path}", method=method)
        request.add_header("Origin", origin)
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        return self._send_headers(request)


def _tokens(*, pool_id: str, client_id: str, password: str) -> dict[str, str]:
    """Mint one ID token per demonstration principal, through the admin API.

    `ADMIN_USER_PASSWORD_AUTH` is enabled on the client for exactly this: an operator or a
    verification run can obtain a real ID token without driving the hosted UI by hand, and the
    flow is reachable only through the IAM-signed `AdminInitiateAuth` call.
    """
    import boto3

    cognito = boto3.client("cognito-idp", region_name="ap-south-1")
    tokens: dict[str, str] = {}
    for role, email in DEMO_USERS.items():
        result = cognito.admin_initiate_auth(
            UserPoolId=pool_id,
            ClientId=client_id,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        tokens[role] = result["AuthenticationResult"]["IdToken"]
    return tokens


def _claims(token: str) -> dict[str, Any]:
    import base64

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def run(
    *, api_url: str, pool_id: str, client_id: str, password: str, console_origin: str, out: Path
) -> int:
    import boto3

    api = Client(api_url)
    sfn = boto3.client("stepfunctions", region_name="ap-south-1")
    flows: list[Flow] = []

    # --- 1. Login -----------------------------------------------------------
    flow = Flow(1, "Login: identity, and what a request without it gets")
    tokens = _tokens(pool_id=pool_id, client_id=client_id, password=password)
    supervisor_claims = _claims(tokens["supervisor"])
    worker_claims = _claims(tokens["worker"])
    flow.observe(
        supervisor={
            "sub_is_uuid": "-" in supervisor_claims["sub"],
            "role": supervisor_claims.get("custom:role"),
            "assigned_site": supervisor_claims.get("custom:assigned_site"),
            "principal_id": supervisor_claims.get("custom:principal_id"),
        },
        worker_principal_id=worker_claims.get("custom:principal_id"),
    )
    flow.require(
        supervisor_claims.get("custom:role") == "supervisor",
        "the supervisor's ID token does not carry custom:role",
    )
    flow.require(
        supervisor_claims.get("custom:assigned_site") == "example-piling-site",
        "the supervisor's ID token does not carry custom:assigned_site",
    )
    flow.require(
        supervisor_claims.get("custom:principal_id") == "supervisor-001",
        "the supervisor's ID token does not carry custom:principal_id",
    )

    no_token_status, no_token_body = api.call("GET", PROTECTED_ROUTE)
    flow.observe(no_token_status=no_token_status, no_token_body=str(no_token_body)[:120])
    flow.require(
        no_token_status == 401,
        f"a request with no token got {no_token_status}, expected 401",
    )
    bad_status, _ = api.call("GET", PROTECTED_ROUTE, token="not-a-jwt")
    flow.require(bad_status == 401, f"a malformed token got {bad_status}, expected 401")

    # CORS, asserted the way a browser enforces it rather than the way curl permits it. Both of
    # these passed end to end once while the deployed console showed "Is the API running?" on every
    # screen: the preflight answered with a list of origins instead of one, and the tokenless 401
    # carried no origin at all, so the browser turned both into `Failed to fetch`.
    preflight_status, preflight_headers = api.preflight(PROTECTED_ROUTE, origin=console_origin)
    allowed = preflight_headers.get("access-control-allow-origin")
    flow.observe(preflight_status=preflight_status, preflight_allow_origin=allowed)
    flow.require(
        preflight_status in (200, 204),
        f"the preflight got {preflight_status}, expected 200 or 204",
    )
    flow.require(
        allowed == console_origin,
        f"the preflight's Access-Control-Allow-Origin is {allowed!r}; a browser accepts only "
        f"{console_origin!r} itself, so an authenticated request from the console fails as "
        "'Failed to fetch' even though this script can read the response",
    )
    refused_status, refused_headers = api.headers_for("GET", PROTECTED_ROUTE, origin=console_origin)
    refused_origin = refused_headers.get("access-control-allow-origin")
    flow.observe(tokenless_status=refused_status, tokenless_allow_origin=refused_origin)
    flow.require(
        refused_status == 401 and refused_origin == console_origin,
        f"a tokenless request returned {refused_status} with "
        f"Access-Control-Allow-Origin={refused_origin!r}; API Gateway answers it before any "
        "Lambda runs, so without that header the browser hides the 401 and the console reports "
        "the API as unreachable",
    )
    flows.append(flow)

    # --- 2. Site selection and the resolution it scopes ---------------------
    flow = Flow(2, "Site selection: resolution scoped to the authenticated supervisor's site")
    status, supervisor = api.call(
        "GET", "/api/supervisor?scenario=replay", token=tokens["supervisor"]
    )
    flow.require(status == 200, f"GET /api/supervisor returned {status}: {supervisor}")
    if status == 200 and isinstance(supervisor, dict):
        site = supervisor.get("site") or {}
        flow.observe(site=site, stage=supervisor.get("stage_detail"))
        flow.require(site.get("site_id") == "example-piling-site", "wrong site in the payload")
        flow.require(
            site.get("activity_type") == "Piling works.",
            "site activity_type is not the seeded fact",
        )
        flow.observe(
            applicable_obligations=sum(
                1 for item in supervisor.get("obligations", []) if item.get("applicable") is True
            )
        )
    flows.append(flow)

    # --- 4. Official invocation --------------------------------------------
    flow = Flow(4, "Official invocation: the stage comes from a CAQM order, and says it is history")
    detail = (supervisor or {}).get("stage_detail", {}) if isinstance(supervisor, dict) else {}
    flow.observe(stage_detail=detail)
    flow.require(detail.get("official_stage") == 3, "the invoked stage is not Stage III")
    flow.require(detail.get("is_replay") is True, "the January invocation is not labelled a replay")
    flow.require(detail.get("lifecycle") == "revoked", "the invocation's lifecycle is not revoked")
    flow.require(
        bool(detail.get("order_doc_id")) and bool(detail.get("order_short_hash")),
        "the invocation does not name the order document that invoked it",
    )
    flows.append(flow)

    # --- 5. Obligation resolution ------------------------------------------
    flow = Flow(5, "Obligation resolution: cited clauses with page, quote and source hash")
    obligations = (supervisor or {}).get("obligations", []) if isinstance(supervisor, dict) else []
    cited = [item for item in obligations if item.get("source_quote") or item.get("citation")]
    flow.observe(obligations=len(obligations), cited=len(cited))
    flow.require(len(obligations) >= 8, "the corpus's obligations are not in the payload")
    flow.require(bool(cited), "no obligation carries a citation")
    for item in obligations[:1]:
        flow.observe(sample_obligation=item)
    flows.append(flow)

    # --- 3. Latest reading --------------------------------------------------
    flow = Flow(3, "Latest reading: a number only ever appears with its provenance")
    status, reading = api.call("GET", "/api/reading/latest")
    flow.observe(status=status, reading=reading)
    flow.require(status == 200, f"GET /api/reading/latest returned {status}")
    if isinstance(reading, dict) and reading.get("available"):
        flow.require(
            reading.get("provenance") in ("replay", "synthetic", "measured"),
            "the reading carries no provenance label",
        )
        flow.require(
            reading.get("is_measured") is False or reading.get("provenance") == "measured",
            "the reading claims to be measured without provenance=measured",
        )
    flows.append(flow)

    # --- 6. Standing Order --------------------------------------------------
    flow = Flow(6, "Standing Order: signed by the authenticated supervisor, and the run starts")
    status, created = api.call(
        "POST", "/api/standing-order", token=tokens["supervisor"], body={"scenario": "replay"}
    )
    flow.require(status == 200, f"POST /api/standing-order returned {status}: {created}")
    order = (created or {}).get("standing_order") or {} if isinstance(created, dict) else {}
    workflow = (created or {}).get("workflow") or {} if isinstance(created, dict) else {}
    flow.observe(order=order, workflow=workflow)
    flow.require(
        order.get("supervisor_id") == "supervisor-001", "the order was signed by someone else"
    )
    flow.require(bool(order.get("commitment_hash")), "the signed order carries no commitment hash")
    flow.require(
        workflow.get("published") is True, f"the StageInvocation was not published: {workflow}"
    )
    flow.require(order.get("status") == "active", f"the order is {order.get('status')}, not active")

    sm_arn = _state_machine_arn()
    event_id = workflow.get("event_id")
    execution = _wait_for_execution(
        sfn, sm_arn, event_id=event_id, want="started", timeout_seconds=300
    )
    flow.observe(state_machine=sm_arn, execution=execution)
    flow.require(execution is not None, "no Step Functions execution was started by the trigger")
    if execution:
        flow.require(
            execution["status"] in ("RUNNING", "SUCCEEDED"),
            f"execution is {execution['status']}: {str(execution.get('cause'))[:200]}",
        )
    flows.append(flow)

    # --- 7. Parchi ----------------------------------------------------------
    flow = Flow(7, "Parchi: one per rostered worker, each behind an opaque token")
    status, roster = api.call("GET", "/api/roster/qr?scenario=replay", token=tokens["supervisor"])
    flow.require(status == 200, f"GET /api/roster/qr returned {status}")
    workers = (roster or {}).get("workers", []) if isinstance(roster, dict) else []
    with_payload = [item for item in workers if item.get("payload")]
    flow.observe(
        workers=len(workers), with_payload=len(with_payload), minted=(roster or {}).get("qr_minted")
    )
    flow.require(len(workers) == 34, f"the roster holds {len(workers)} workers, expected 34")
    flow.require(len(with_payload) == 34, f"only {len(with_payload)} Parchis carry a QR payload")
    if with_payload:
        sample = with_payload[0]["payload"]
        flow.observe(sample_payload_prefix=sample[:24])
        flow.require(sample.startswith("aadesh://ack/"), "the QR payload is not the aadesh scheme")
        flow.require(
            "worker-" not in sample.split("aadesh://ack/")[1]
            and "parchi-" not in sample.split("aadesh://ack/")[1],
            "the QR payload names a worker or a parchi in the clear",
        )
    flows.append(flow)

    # --- 8. Worker acknowledgement, and the seal it makes possible ----------
    flow = Flow(8, "Worker acknowledgement: the worker confirms, a proxy attempt does not")
    if not with_payload:
        flow.failures.append("no Parchi payload to acknowledge")
        flows.append(flow)
    else:
        first = with_payload[0]
        status, view = api.call("POST", "/api/worker/view", body={"payload": first["payload"]})
        flow.require(status == 200, f"POST /api/worker/view returned {status}")
        flow.observe(
            view_state=(view or {}).get("state"),
            citations=len((view or {}).get("citations") or []),
            obligations=len((view or {}).get("obligation_ids") or []),
        )
        flow.require(bool((view or {}).get("citations")), "the Parchi carries no verified citation")

        # The fresh acknowledgement can be exercised ONCE per corpus fingerprint. Parchi ids are
        # deterministic from (fingerprint, worker_id) and the store is persistent, so a second run
        # finds this worker's Parchi already acknowledged and is served the first run's result by
        # the idempotency ledger -- which is the ledger doing its job, not a defect. Nothing here
        # retries its way to green, so the honest report is SKIP with that reason rather than FAIL.
        # Everything the state still allows is asserted either way: the citation above, the refusal
        # of a proxy attempt below, and the Parchi's own transition.
        already_acknowledged = (view or {}).get("state") != "pending_ack"
        if already_acknowledged:
            flow.skip(
                f"the Parchi is already {(view or {}).get('state')}: parchi ids are deterministic "
                "from (fingerprint, worker_id), so a re-run is served the first run's result and "
                "no fresh acknowledgement exists to prove"
            )

        # Worker A's token with worker B's name: the domain must refuse it.
        proxy_status, proxy_body = api.call(
            "POST",
            "/api/worker/acknowledge",
            body={"payload": first["payload"], "worker_id": "worker-009"},
        )
        flow.observe(proxy_status=proxy_status, proxy_body=str(proxy_body)[:160])
        flow.require(
            proxy_status == 403,
            f"naming another worker returned {proxy_status}, expected 403",
        )

        acked = 0
        for item in with_payload:
            status, body = api.call(
                "POST",
                "/api/worker/acknowledge",
                body={"payload": item["payload"], "worker_id": item["worker_id"]},
            )
            if status == 200:
                acked += 1
            elif status not in (400,):  # an already-acknowledged Parchi is a 400 by design
                flow.failures.append(f"acknowledging {item['worker_id']} returned {status}: {body}")
        flow.observe(acknowledged=acked)

        status, after = api.call("POST", "/api/worker/view", body={"payload": first["payload"]})
        flow.observe(state_after_ack=(after or {}).get("state"))
        flow.require(
            (after or {}).get("state") in ("acknowledged", "sealed"), "the Parchi did not move on"
        )

        # The map state settles only when EVERY branch has resolved, and the seal is the next
        # step after it -- so the run is what proves sealing, not this script's optimism. On a
        # re-run there is no fresh token left to resume (the replay path performs no
        # SendTaskSuccess), so waiting could only measure the timeout rather than the machine.
        if already_acknowledged:
            flow.observe(
                execution_final="not waited for: a re-run resumes nothing, so this run's map "
                "state cannot reach a terminal state"
            )
        else:
            finished = _wait_for_execution(
                sfn, sm_arn, event_id=event_id, want="terminal", timeout_seconds=900
            )
            flow.observe(execution_final=finished)
            if finished:
                flow.require(
                    finished["status"] == "SUCCEEDED",
                    f"the run ended {finished['status']}: {str(finished.get('cause'))[:200]}",
                )
        status, impact = api.call("GET", "/api/impact")
        sealed = ((impact or {}).get("metrics") or {}).get(
            "workers_with_documented_displacement", {}
        )
        flow.observe(public_impact_documented=(sealed or {}).get("count"))
        flows.append(flow)

    # --- 9. Cedar denial ----------------------------------------------------
    flow = Flow(9, "Cedar denial: a supervisor cannot acknowledge on a worker's behalf")
    status, denial = api.call(
        "POST",
        "/api/cedar/supervisor-acknowledge",
        token=tokens["supervisor"],
        body={"worker_id": "worker-002"},
    )
    flow.observe(status=status, body=denial)
    flow.require(status == 200, f"the Cedar demonstration route returned {status}")
    if isinstance(denial, dict):
        flow.require(
            denial.get("allowed") is False, "the supervisor WAS allowed to proxy an acknowledgement"
        )
        flow.require(
            denial.get("policy_id") == "no-proxy-acknowledgement",
            f"the denial cites {denial.get('policy_id')!r}, not no-proxy-acknowledgement",
        )
    flows.append(flow)

    # --- 10. Facilitator redaction -----------------------------------------
    flow = Flow(10, "Facilitator: assistance under consent, never the worker's record")
    status, facilitator = api.call("GET", "/api/facilitator", token=tokens["facilitator"])
    flow.observe(status=status, body=facilitator)
    flow.require(status == 200, f"GET /api/facilitator returned {status}: {facilitator}")
    if isinstance(facilitator, dict):
        decisions = json.dumps(facilitator)
        flow.require("assist" in decisions.lower(), "no assist decision is reported")
    flows.append(flow)

    # --- 11. Verification ---------------------------------------------------
    flow = Flow(11, "Verification: the deployed corpus re-proves, and tamper detection fires")
    status, verify = api.call("GET", "/api/verify", token=tokens["supervisor"])
    flow.require(status == 200, f"GET /api/verify returned {status}")
    if isinstance(verify, dict):
        main = verify.get("verify") or {}
        tamper = verify.get("tamper") or {}
        flow.observe(
            verify_exit=main.get("exit_code"),
            verify_passed=main.get("passed"),
            citation_lines=_citation_count(main.get("output", "")),
            tamper_exit=tamper.get("exit_code"),
            tamper_caught=tamper.get("caught"),
        )
        flow.require(main.get("exit_code") == 0, f"make verify exited {main.get('exit_code')}")
        flow.require(tamper.get("exit_code") == 1, "the tamper check did not fail as expected")
    flows.append(flow)

    # --- 12. AI explanation -------------------------------------------------
    flow = Flow(12, "Explanation: a model may rephrase, never decide, and says which it is")
    status, explain = api.call(
        "POST", "/api/explain", token=tokens["supervisor"], body={"scenario": "replay"}
    )
    flow.require(status == 200, f"POST /api/explain returned {status}: {explain}")
    if isinstance(explain, dict):
        flow.observe(
            status=explain.get("status"),
            source=((explain.get("explanation") or {}).get("source")),
            model=explain.get("model"),
            violations=explain.get("violations"),
        )
        flow.require(
            bool((explain.get("deterministic") or {}).get("text")),
            "no deterministic text was computed, so there is nothing to fall back on",
        )
        flow.require(
            (explain.get("explanation") or {}).get("source")
            in ("deterministic", "model", "bedrock"),
            f"the explanation's source is {((explain.get('explanation') or {}).get('source'))!r}",
        )
    flows.append(flow)

    report = {
        "api_url": api_url,
        "user_pool_id": pool_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "flows": [flow.as_dict() for flow in flows],
        "passed": sum(1 for flow in flows if flow.status == "PASS"),
        "failed": sum(1 for flow in flows if flow.status == "FAIL"),
        "skipped": sum(1 for flow in flows if flow.status == "SKIP"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    for flow in flows:
        print(f"[{flow.status}] {flow.number:>2}. {flow.name}")
        for failure in flow.failures:
            print(f"          - {failure}")
        for reason in flow.skips:
            print(f"          - skipped: {reason}")

    print(
        f"\n{report['passed']} passed, {report['failed']} failed, "
        f"{report['skipped']} skipped. Evidence: {out}"
    )
    return 1 if report["failed"] else 0


def _citation_count(output: str) -> int | None:
    for line in output.splitlines():
        if "entries checked" in line and ":" in line:
            try:
                return int(line.split(":")[-1].strip())
            except ValueError:
                return None
    return None


def _console_origin(stack_name: str = "aadesh-prod") -> str:
    """The console's origin, read from the deployed stack rather than assumed.

    It has to be the origin the API was configured to allow, byte for byte -- that is the whole
    point of the assertion -- so it is taken from the stack's own `AmplifyDefaultDomain` output.
    """
    import boto3

    outputs = (
        boto3.client("cloudformation", region_name="ap-south-1")
        .describe_stacks(StackName=stack_name)["Stacks"][0]
        .get("Outputs", [])
    )
    for output in outputs:
        if output["OutputKey"] == "AmplifyDefaultDomain":
            return f"https://{output['OutputValue']}"
    raise SystemExit(f"{stack_name} has no AmplifyDefaultDomain output to take an origin from.")


def _state_machine_arn() -> str:
    import boto3

    machines = (
        boto3.client("stepfunctions", region_name="ap-south-1")
        .list_state_machines()
        .get("stateMachines", [])
    )
    for machine in machines:
        if machine["name"].endswith("-standing-order"):
            return machine["stateMachineArn"]
    raise SystemExit("No *-standing-order state machine found in ap-south-1.")


TERMINAL_STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED")


def _wait_for_execution(
    sfn: Any,
    machine_arn: str,
    *,
    event_id: str | None,
    want: str,
    timeout_seconds: int = 300,
) -> dict[str, Any] | None:
    """Poll for the execution this run started.

    Matched by event id: EventBridge names an execution `<event-id>_<rule-hash>`, so the event id
    the publish returned is the only reliable link between "I published a trigger" and "a run
    exists for it". Without that link this would happily report somebody else's execution.

    `want="started"` accepts any status -- a run that already failed still proves the trigger
    worked, and reporting it as missing would hide the failure. `want="terminal"` waits for the
    run to settle.
    """
    deadline = time.time() + timeout_seconds
    while True:
        executions = sfn.list_executions(stateMachineArn=machine_arn, maxResults=20).get(
            "executions", []
        )
        for execution in executions:
            if event_id and not execution["name"].startswith(event_id):
                continue
            if want == "terminal" and execution["status"] not in TERMINAL_STATUSES:
                continue
            described = sfn.describe_execution(executionArn=execution["executionArn"])
            return {
                "name": execution["name"],
                "status": execution["status"],
                "started_at": execution["startDate"].isoformat(),
                "arn": execution["executionArn"],
                "cause": described.get("cause"),
            }
        if time.time() >= deadline:
            return None
        time.sleep(10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--user-pool-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument(
        "--password",
        default=None,
        help="the seeded demo users' password; defaults to .deploy/demo-users.json",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--console-origin",
        default=None,
        help="the console's origin, exactly as API Gateway allows it; defaults to the deployed "
        "stack's AmplifyDefaultDomain output",
    )
    args = parser.parse_args(argv)

    password = args.password
    if not password:
        credentials = (REPO_ROOT / ".deploy" / "demo-users.json").read_text(encoding="utf-8")
        password = json.loads(credentials)["password"]

    return run(
        api_url=args.api_url,
        pool_id=args.user_pool_id,
        client_id=args.client_id,
        password=password,
        console_origin=args.console_origin or _console_origin(),
        out=args.out,
    )


if __name__ == "__main__":
    raise SystemExit(main())
