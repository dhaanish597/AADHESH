# Phase 1 — Adapters and the `AadeshApplication` Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the deterministic core run against AWS-shaped adapters — DynamoDB, S3, OpenAQ, CloudWatch — with the same ports and the same semantics as the in-memory ones, and extract a shared `AadeshApplication` that both the local `http.server` skin and a Lambda skin drive, all proven offline plus optionally against LocalStack.

**Architecture:** No core logic changes. Every new capability crosses an existing `typing.Protocol` port; the only new port is `TaskTokenStore`, which the committed Step Functions ASL already depends on and which nothing implements today. Adapters are held to the in-memory reference implementations by one contract suite parametrised over both, so "the AWS path behaves like the tested path" is a test result rather than a claim.

**Tech Stack:** Python 3.13, `cedarpy==4.12.1`, `jsonschema`, `boto3` (opt-in `aws` extra), pytest, ruff, LocalStack via Docker.

**Spec:** `docs/superpowers/specs/2026-10-09-aadesh-aws-deployment-design.md`

## Roadmap

This plan covers **Phase 1 only**. Phases 2–5 each get their own plan when their predecessor has actually landed, because they describe CDK constructs and Lambda ARNs that cannot exist until this phase's interfaces are real.

| Phase | Deliverable | Plan |
|---|---|---|
| **1** | Adapters + `AadeshApplication` refactor, contract-tested | **this document** |
| 2 | CDK `AadeshData` + `AadeshBackend`, corpus synced with a deploy-time checksum assertion, first real URL | not yet written |
| 3 | CDK `AadeshIdentity`, JWT authorizer, principal from verified claims, frontend login | not yet written |
| 4 | `workflow` Lambda, ASL `TimeoutSeconds` fix, task-token round trip, `SendTaskSuccess` | not yet written |
| 5 | Amplify, README AWS resource table, `.env.example`, the 12 recorded verification flows | not yet written |

Phase 1 produces no AWS resources and changes no deployed behaviour. It is the phase that makes phases 2–5 possible.

## Global Constraints

Copied verbatim from the spec and the existing repo configuration. Every task's requirements implicitly include this section.

- `requires-python = ">=3.13"`; the interpreter is **3.13.14**.
- `cedarpy==4.12.1` is **pinned** and must not be bumped. The authorization boundary must not drift.
- `ruff` config: `line-length = 100`, `target-version = "py313"`, `select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]`, and `"tests/**" = ["E501"]`.
- `pytest` runs with `addopts = "-ra --strict-markers --strict-config"`. **A new marker must be declared in `[tool.pytest.ini_options].markers` or the whole suite errors.** `integration` and `requires_index` are already declared; no new marker is needed by this plan.
- `pythonpath = ["services"]`, so `aadesh_core` and `aadesh_adapters` import without an install step.
- **The default path must never require Docker, AWS credentials or a network.** `make test` and `make verify` stay offline. Anything needing Docker or AWS is opt-in and marked `integration`.
- `tests/conftest.py` sets `AADESH_ENV=test` via `os.environ.setdefault` at import.
- `aadesh_core` imports **no** boto3, requests, or any AWS SDK. Test `test_authorization_no_model.py` and `test_explanation_no_model.py` enforce the import-boundary pattern; new core code must not break it.
- AWS adapters must import `boto3` **lazily**, as `explain/bedrock.py` already does, because `boto3` lives in the opt-in `aws` extra.
- Region is `ap-south-1`. Bedrock is pinned to `us-east-1`.
- DynamoDB tables: `aadesh-parchis`, `aadesh-operational`, `aadesh-standing-orders`, `aadesh-trigger-runs`, `aadesh-readings`, `aadesh-sites`.
- S3 bucket: `aadesh-sources-375546530800-ap-south-1`.
- SSM parameters: `/aadesh/prod/openaq-api-key`, `/aadesh/prod/qr-signing-secret`.
- `AWS_ENDPOINT_URL`, when set, must be honoured by every AWS adapter (`.env.example` already documents it: "Point at LocalStack for `make test-integration`; leave blank for real AWS").
- `aadesh_core/ports/__init__.py` does **not** re-export `ParchiAckStore`, `AcknowledgementTokenStore` or `IdempotencyLedger`. Import those from `aadesh_core.ports.parchi_ack`.
- Every port Protocol is decorated `@runtime_checkable`.
- **No secrets, keys, credentials or personal data may be committed.**
- Commit messages end with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.

## Review Focus

Five input classes and failure modes the spec implies but that no existing test exercises, most likely to bite a real user, with the task that pins each one.

1. **A `Parchi` field silently dropped or renamed by serialisation.** An evidence record that round-trips through DynamoDB minus one field is not the record that was signed; a lost `content_hash` or a reordered `obligation_ids` makes the parchi unverifiable while still looking complete. → Task 3.
2. **`execute_once` whose first caller dies mid-`compute`.** If the key is left claimed, that worker can never acknowledge — permanently, silently, and only for the one worker who hit the crash. → Task 7.
3. **Two concurrent confirmations racing on one token.** Both succeeding would produce two acknowledgements of one displacement. The loser must lose, and must lose by raising rather than by returning quietly. → Task 6.
4. **A stale or half-written materialised corpus.** Verification that hashes yesterday's bytes, or a `/tmp` tree left truncated by a crash mid-sync, reports on a corpus that is not the one in S3. → Task 10.
5. **An OpenAQ response whose parameter or unit does not match what we asked for.** Storing a plausible-looking number as `MEASURED` is worse than storing nothing, because the whole point of the provenance enum is that a measurement means a measurement. `StationReading` has no `unit` field at all, so a unit the provider does not confirm must reject the reading rather than be dropped on the floor. → Task 11.

---

## File Structure

**New — core port**
- `services/aadesh_core/ports/task_token.py` — the `TaskTokenStore` Protocol. One responsibility: durably hold a Step Functions task token between the Lambda that receives it and the Lambda that resumes the machine.
- `services/aadesh_core/ports/__init__.py` — modified to export `TaskTokenStore`.

**New — in-memory adapters**
- `services/aadesh_adapters/store/memory_task_token.py` — `InMemoryTaskTokenStore`, the reference the DynamoDB one is held to.
- `services/aadesh_adapters/store/memory_standing_order.py` — `InMemoryStandingOrderStore`, `InMemoryTriggerRunStore`. Neither exists today; `server.py` holds the single standing order in a field.

**New — DynamoDB package**
- `services/aadesh_adapters/store/dynamo/__init__.py` — exports.
- `services/aadesh_adapters/store/dynamo/client.py` — table names, lazy client/resource construction honouring `AWS_ENDPOINT_URL`, and the conditional-write error translation. The one place boto3 is touched for the store.
- `services/aadesh_adapters/store/dynamo/serde.py` — explicit, versioned round-trip serialisation for `Parchi`, `AcknowledgementToken`, `StandingOrder`, `TriggerRun`. Fails loudly on an unknown or missing field.
- `services/aadesh_adapters/store/dynamo/parchi.py` — `DynamoParchiStore`.
- `services/aadesh_adapters/store/dynamo/ack.py` — `DynamoAcknowledgementTokenStore` (compare-and-set).
- `services/aadesh_adapters/store/dynamo/ledger.py` — `DynamoIdempotencyLedger` (the lease/placeholder design with crash recovery).
- `services/aadesh_adapters/store/dynamo/task_token.py` — `DynamoTaskTokenStore` (delete-on-read).
- `services/aadesh_adapters/store/dynamo/standing_order.py` — `DynamoStandingOrderStore`, `DynamoTriggerRunStore` (`claim` is create-if-absent).

**New — other adapters**
- `services/aadesh_adapters/corpus/s3.py` — `S3Corpus`, materialising to `/tmp` keyed by the S3 `versionId` of `manifest.json`.
- `services/aadesh_adapters/aqi/openaq.py` — `OpenAQProvider`, stamping `Provenance.MEASURED` only for an attributed parameter.
- `services/aadesh_adapters/audit/cloudwatch.py` — `CloudWatchAuditLog`, structured stdout plus an EMF metric for denials.

**New — application**
- `services/aadesh_app/__init__.py`
- `services/aadesh_app/application.py` — `AadeshApplication`: the port-injected logic currently inside `Demo`.
- `services/aadesh_app/routes.py` — the one declarative route table both skins read.
- `services/aadesh_lambda/__init__.py`
- `services/aadesh_lambda/handlers/__init__.py`
- `services/aadesh_lambda/handlers/api.py` — the API Gateway skin.

**Modified**
- `services/aadesh_web/server.py` — `Demo` becomes a thin `http.server` skin over `AadeshApplication`; `_payloads` is deleted (see Task 13).
- `services/aadesh_adapters/store/__init__.py`, `tests/contract/test_aqi_provider_contract.py` (OpenAQ joins `ADAPTERS`).
- `tests/support/source_scan.py` — gains a secrets rule.
- `pyproject.toml` — `aadesh_app` and `aadesh_lambda` join `[tool.hatch.build.targets.wheel].packages`.

**New — tests and infra**
- `tests/contract/conftest.py` — LocalStack fixtures, `integration`-marked.
- `tests/contract/test_parchi_store_contract.py`, `test_ack_token_store_contract.py`, `test_idempotency_ledger_contract.py`, `test_task_token_store_contract.py`, `test_standing_order_store_contract.py`
- `tests/unit/test_dynamo_serde.py`, `test_s3_corpus.py`, `test_openaq_provider.py`, `test_cloudwatch_audit.py`, `test_application_routes.py`
- `tests/verification/test_skin_parity.py`
- `docker-compose.yml` — LocalStack, for `make test-integration`.
- `Makefile` — a `localstack` target. The integration path needs no `AWS_ENDPOINT_URL` default: the `dynamo_tables` fixture pins it (Task 4).

---

### Task 1: `TaskTokenStore` port and its in-memory adapter

The committed ASL passes `task_token.$: "$$.Task.Token"` to `aadesh-parchi-ack-waiter`, and nothing in the repo can store it. Without this port a worker's acknowledgement cannot resume the waiting execution, so it is first.

**Files:**
- Create: `services/aadesh_core/ports/task_token.py`
- Modify: `services/aadesh_core/ports/__init__.py`
- Create: `services/aadesh_adapters/store/memory_task_token.py`
- Test: `tests/unit/test_task_token_store.py`

**Interfaces:**
- Produces: `TaskTokenStore` Protocol with `put(*, parchi_id: str, task_token: str, expires_at: datetime) -> None`, `pop(*, parchi_id: str) -> str | None`, `peek(*, parchi_id: str) -> str | None`; `InMemoryTaskTokenStore` satisfying it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_task_token_store.py
"""The token that lets a worker's acknowledgement resume a waiting execution.

Stored on receive, removed on read. Delete-on-read is what makes a retried resume a no-op
instead of a second SendTaskSuccess.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.memory_task_token import InMemoryTaskTokenStore
from aadesh_core.ports.task_token import TaskTokenStore

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
def store() -> InMemoryTaskTokenStore:
    return InMemoryTaskTokenStore()


def test_satisfies_the_port(store) -> None:
    assert isinstance(store, TaskTokenStore)


def test_pop_returns_the_token_once(store) -> None:
    store.put(parchi_id="parchi-001", task_token="tok-abc", expires_at=NOW + timedelta(hours=24))
    assert store.pop(parchi_id="parchi-001") == "tok-abc"
    assert store.pop(parchi_id="parchi-001") is None, "a second pop must not yield the token again"


def test_peek_does_not_remove(store) -> None:
    store.put(parchi_id="parchi-001", task_token="tok-abc", expires_at=NOW + timedelta(hours=24))
    assert store.peek(parchi_id="parchi-001") == "tok-abc"
    assert store.peek(parchi_id="parchi-001") == "tok-abc"


def test_unknown_parchi_returns_none_rather_than_raising(store) -> None:
    assert store.pop(parchi_id="nope") is None


def test_naive_expiry_is_refused(store) -> None:
    """A naive expiry compared against timezone-aware Lambda clock reads expires early or
    late depending on the host. Refuse it at the door."""
    with pytest.raises(ValueError, match="timezone-aware"):
        store.put(
            parchi_id="parchi-001",
            task_token="tok-abc",
            expires_at=datetime(2026, 10, 10, 9, 0),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_task_token_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_core.ports.task_token'`

- [ ] **Step 3: Write the port**

```python
# services/aadesh_core/ports/task_token.py
"""Where a Step Functions task token waits for its worker.

The ASL holds each parchi in PENDING_ACK with `lambda:invoke.waitForTaskToken`. That call
returns immediately; the machine resumes only when someone calls SendTaskSuccess with the
token. The token therefore has to survive between two different Lambda invocations, possibly
on two different containers, possibly hours apart.

Deliberately narrow: a token is stored against a parchi id and read back once. There is no
enumeration and no listing, for the same reason `AcknowledgementTokenStore` has none -- a
capability to list every suspended execution is a capability nobody needs.

**What `expires_at` is and is not.** It is a hint to the storage layer, not a rule this port
enforces: neither signature takes a `now`, so neither implementation can decide that a token
has expired. The in-memory adapter keeps a token until it is popped; the DynamoDB adapter
sets a TTL that reclaims the item some time after `expires_at`. Those differ, and the contract
suite deliberately does not test expiry for that reason. Expiry of the *machine* is enforced
by Step Functions, which rejects a task token past its timeout -- that is the guarantee that
matters, and it does not depend on this store. `expires_at` exists so the store does not
retain a token indefinitely.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class TaskTokenStore(Protocol):
    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None:
        """Record the token for `parchi_id`. MUST refuse a naive `expires_at`."""
        ...

    def pop(self, *, parchi_id: str) -> str | None:
        """Read the token AND remove it, as one operation.

        Removing on read is the property that makes a retried resume safe: the second attempt
        finds nothing and does not call SendTaskSuccess twice. Returns None when there is no
        token, which is an ordinary condition -- the machine may already have timed out.
        """
        ...

    def peek(self, *, parchi_id: str) -> str | None:
        """Read without removing, for diagnostics. MUST NOT be used to resume a machine."""
        ...
```

- [ ] **Step 4: Export it**

In `services/aadesh_core/ports/__init__.py`, add the import alongside the others and `"TaskTokenStore"` to `__all__`, keeping the list alphabetical:

```python
from aadesh_core.ports.task_token import TaskTokenStore
```

- [ ] **Step 5: Write the in-memory adapter**

```python
# services/aadesh_adapters/store/memory_task_token.py
"""In-memory TaskTokenStore. The reference the DynamoDB adapter is held to."""

from __future__ import annotations

import threading
from datetime import datetime


class InMemoryTaskTokenStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}

    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None:
        if expires_at.tzinfo is None:
            raise ValueError(
                "TaskTokenStore.put requires a timezone-aware expires_at. A naive datetime "
                "would be compared against the Lambda clock in an unknown zone."
            )
        with self._lock:
            self._tokens[parchi_id] = task_token

    def pop(self, *, parchi_id: str) -> str | None:
        with self._lock:
            return self._tokens.pop(parchi_id, None)

    def peek(self, *, parchi_id: str) -> str | None:
        with self._lock:
            return self._tokens.get(parchi_id)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_task_token_store.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add services/aadesh_core/ports/task_token.py services/aadesh_core/ports/__init__.py \
        services/aadesh_adapters/store/memory_task_token.py tests/unit/test_task_token_store.py
git commit -m "feat(ports): add TaskTokenStore, which the committed ASL already needs"
```

---

### Task 2: In-memory `StandingOrderStore` and `TriggerRunStore`

Both ports exist and neither has any implementation — not even in-memory. `server.py` keeps its single order in `self.order`, so nothing today can exercise the `TriggerRunStore.claim` idempotency contract against a real adapter.

**Files:**
- Create: `services/aadesh_adapters/store/memory_standing_order.py`
- Create: `tests/unit/test_standing_order_store_memory.py`
- Modify: `tests/support/builders.py` — gains the shared `standing_order(...)` factory (Step 1)
- Modify: `tests/unit/test_standing_order_lifecycle.py` — imports that factory, drops its private `_order`

**Interfaces:**
- Consumes: `StandingOrder`, `TriggerRun` from `aadesh_core.standing_order.models`; the ports from `aadesh_core.standing_order.ports`.
- Produces: `InMemoryStandingOrderStore` (`get`, `save`, `for_site`), `InMemoryTriggerRunStore` (`claim`, `get`, `complete`), and `standing_order(**over)` in `tests/support/builders.py`.

- [ ] **Step 1: Promote the standing-order test factory into the shared builders module**

`tests/unit/test_standing_order_lifecycle.py` has a keyword-only `_order(...)` factory at line 45 that builds a valid `StandingOrder`, and three other test files build one inline. Move it to `tests/support/builders.py` as `standing_order(...)` so this task and the contract suites share one definition, then have `test_standing_order_lifecycle.py` import it and drop its private copy.

**This is a pure move, and that is the whole point.** Keep the parameter names, the defaults and the body exactly as they are in the existing `_order` — the 16 call sites in that file are keyword-only and feed off those defaults, so changing them silently rewrites what the lifecycle tests assert. Read `services/aadesh_core/standing_order/models.py` before editing: `StandingOrder.__post_init__` (line 180) refuses an empty `actions` tuple, requires timezone-aware instants with `valid_from < valid_until`, and allows `signed_at=None`; `StandingOrderActionClause.__post_init__` (line 109) freezes `parameters` itself, so `frozendict({})` and `{}` both land on a frozendict.

Two details the move must get right, neither of them visible from the destination file alone:

- **`fingerprint` is not a `StandingOrder` field.** The factory's `fingerprint` parameter maps to `trigger_fingerprint` (line 88 of the file you are moving from; called as `_order(..., fingerprint="abc123")` at line 128). Keep the parameter named `fingerprint`, and keep that mapping.
- **`uuid4` does not exist in `builders.py` yet, and `timedelta` is not needed at all.** Its import block is `from datetime import UTC, datetime` / `from typing import Any` (lines 10-11). The factory body imports `uuid4` function-locally, so it needs nothing new — and it never mentions `timedelta`: the validity window comes from the module constants `VALID_FROM`/`VALID_UNTIL`, which move across with `NOW`. `timedelta` appears in that file's *tests*, which import it themselves and keep doing so. **Do not add `timedelta` to `builders.py`** — nothing there would use it, and an unused import is ruff `F401`, which `make lint` fails on (`tests/**` relaxes only `E501`). For the same reason, merge any names you do need into the existing block rather than appending a second import group, since `ruff`'s `I` rules are enabled and an unsorted import also fails the lint gate. Trust `uv run ruff check tests` over this list: if it reports an unused import, delete it.

**Copy the factory body from the file — do not retype it from this plan.** Roughly: a `def standing_order(*, status=StandingOrderStatus.DRAFT, valid_from=VALID_FROM, valid_until=VALID_UNTIL, signed_at=None, commitment_hash=None, triggered_at=None, completed_at=None, expired_at=None, supervisor_id="sup-1", site_id="site-001", trigger=None, actions=None, fingerprint=None) -> StandingOrder` that builds a `StageInvocationTrigger(stage=3, match=EXACT, type=OFFICIAL_STAGE_INVOCATION)` and a one-element `StandingOrderActionClause(action=ISSUE_HALT, parameters=frozendict({}))` when those arguments are `None`, and passes `standing_order_id=str(uuid4())`, `created_at=NOW` and `trigger_fingerprint=fingerprint`. It uses the module-level `NOW`; move that constant across with it.

Names to merge into `tests/support/builders.py`'s existing block:

```python
from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)
from aadesh_core.standing_order.models import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    frozendict,
)
```

`from datetime import UTC, datetime`, `from typing import Any` and the `aadesh_core.domain` import are already there and stay as they are. `uuid4` and `timedelta` are deliberately absent — see the bullet above. Let `uv run ruff check tests` decide the final list; it is the authority, not this block.

Then in `tests/unit/test_standing_order_lifecycle.py`: delete the `_order` definition, add `from tests.support.builders import standing_order`, and rename its 16 `_order(` call sites to `standing_order(`. Finally run `uv run ruff check tests` and delete **exactly** the imports it reports as unused in that file — no others; several are still live.

Run: `uv run pytest tests/unit/test_standing_order_lifecycle.py tests/unit/test_standing_order_trigger.py -q`
Expected: PASS, unchanged — the same tests and the same assertions as before the move. If any assertion changed, the move was not pure; revert and redo it.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_standing_order_store_memory.py
"""The trigger fingerprint is the chokepoint that makes duplicate parchis unrepresentable."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from aadesh_adapters.store.memory_standing_order import (
    InMemoryStandingOrderStore,
    InMemoryTriggerRunStore,
)
from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import TriggerRun
from tests.support.builders import standing_order

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def run(*, fingerprint="fp-1", parchi_ids=("parchi-001",)) -> TriggerRun:
    """`TriggerRun.__post_init__` refuses an empty `parchi_ids`, so the default is non-empty."""
    return TriggerRun(
        fingerprint=fingerprint,
        standing_order_id="so-1",
        site_id="example-piling-site",
        stage=3,
        order_doc_id="order-001",
        order_sha256="a" * 64,
        started_at=NOW,
        status=StandingOrderStatus.TRIGGERED,
        parchi_ids=tuple(parchi_ids),
    )


def test_claim_creates_when_absent() -> None:
    store = InMemoryTriggerRunStore()
    claimed = store.claim(run())
    assert claimed.fingerprint == "fp-1"
    assert store.get("fp-1") is not None


def test_claim_returns_the_existing_run_and_does_not_overwrite() -> None:
    """This is the whole contract. A redelivered trigger must not mint a second set."""
    store = InMemoryTriggerRunStore()
    store.claim(run(parchi_ids=("parchi-001",)))
    second = store.claim(run(parchi_ids=("parchi-999",)))
    assert second.parchi_ids == ("parchi-001",), "claim overwrote an existing run"


def test_complete_is_idempotent() -> None:
    store = InMemoryTriggerRunStore()
    store.claim(run())
    store.complete("fp-1", completed_at=NOW)
    first = store.get("fp-1")
    store.complete("fp-1", completed_at=NOW)
    assert store.get("fp-1").completed_at == first.completed_at


def test_complete_on_an_unknown_fingerprint_raises() -> None:
    store = InMemoryTriggerRunStore()
    with pytest.raises(KeyError):
        store.complete("no-such-fingerprint")


def test_standing_order_round_trips() -> None:
    store = InMemoryStandingOrderStore()
    order = standing_order()
    store.save(order)
    assert store.get(order.standing_order_id) == order


def test_for_site_returns_only_that_sites_orders() -> None:
    store = InMemoryStandingOrderStore()
    mine = standing_order(site_id="example-piling-site")
    theirs = standing_order(site_id="some-other-site")
    store.save(mine)
    store.save(theirs)
    assert [o.standing_order_id for o in store.for_site("example-piling-site")] == [
        mine.standing_order_id
    ]


def test_save_replaces_an_order_under_the_same_id() -> None:
    """DRAFT -> CONFIRMED is a legitimate replace of the same id, and the store must allow it."""
    store = InMemoryStandingOrderStore()
    order = standing_order(status=StandingOrderStatus.DRAFT, signed_at=None)
    store.save(order)
    store.save(replace(order, status=StandingOrderStatus.CONFIRMED, signed_at=NOW))
    assert store.get(order.standing_order_id).status is StandingOrderStatus.CONFIRMED
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_standing_order_store_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.store.memory_standing_order'`

- [ ] **Step 4: Write the adapter**

`StandingOrder` and `TriggerRun` are `frozen=True, slots=True`, so transitions use `dataclasses.replace`. Read their exact field lists from `services/aadesh_core/standing_order/models.py` before writing; do not retype them from memory.

```python
# services/aadesh_adapters/store/memory_standing_order.py
"""In-memory Standing Orders persistence. The reference for the DynamoDB adapters.

`TriggerRunStore.claim` is create-if-absent and returns the EXISTING run on a collision. It
does not raise. Raising would push the redelivery decision back onto the caller, and the
caller is a Step Functions retry that has no way to make it.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import StandingOrder, TriggerRun


class InMemoryStandingOrderStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: dict[str, StandingOrder] = {}

    def get(self, standing_order_id: str) -> StandingOrder | None:
        with self._lock:
            return self._orders.get(standing_order_id)

    def save(self, order: StandingOrder) -> None:
        with self._lock:
            self._orders[order.standing_order_id] = order

    def for_site(self, site_id: str) -> Sequence[StandingOrder]:
        with self._lock:
            return tuple(o for o in self._orders.values() if o.site_id == site_id)


class InMemoryTriggerRunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, TriggerRun] = {}

    def claim(self, run: TriggerRun) -> TriggerRun:
        with self._lock:
            existing = self._runs.get(run.fingerprint)
            if existing is not None:
                return existing
            self._runs[run.fingerprint] = run
            return run

    def get(self, fingerprint: str) -> TriggerRun | None:
        with self._lock:
            return self._runs.get(fingerprint)

    def complete(self, fingerprint: str, *, completed_at: datetime | None = None) -> None:
        with self._lock:
            existing = self._runs.get(fingerprint)
            if existing is None:
                raise KeyError(f"No trigger run for fingerprint {fingerprint!r}.")
            if existing.completed_at is not None:
                return
            self._runs[fingerprint] = replace(
                existing,
                status=StandingOrderStatus.COMPLETED,
                completed_at=completed_at or datetime.now(UTC),
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_standing_order_store_memory.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add services/aadesh_adapters/store/memory_standing_order.py \
        tests/support/builders.py tests/unit/test_standing_order_lifecycle.py \
        tests/unit/test_standing_order_store_memory.py
git commit -m "feat(adapters): implement the two standing-order ports that had no adapter"
```

---

### Task 3: Round-trip serialisation for the stored records

`Parchi` has no `to_dict`/`from_dict` anywhere in the repo — only `ConstructionSite.from_dict` and `ExplanationResponse.from_payload` exist. DynamoDB therefore cannot store a parchi until this is written. Doing it generically from the dataclass type hints, with a loud failure on any field mismatch, is what stops a future added field from being silently dropped.

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/__init__.py` (empty)
- Create: `services/aadesh_adapters/store/dynamo/serde.py`
- Test: `tests/unit/test_dynamo_serde.py`

**Interfaces:**
- Produces: `dumps(value: Any) -> dict[str, Any]`, `loads(payload: Mapping[str, Any], hint: type[T]) -> T`, and `SerdeError`. Every DynamoDB adapter uses these four lines apart; nothing else serialises a core record.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dynamo_serde.py
"""DynamoDB stores evidence records. A serde that drops a field makes them unverifiable.

`dataclasses.asdict` is not usable here: it renders a StrEnum as a bare string with no
schema, erases the distinction between an absent key and a None value, and silently ignores a
field added later. Each of those is a way for a stored parchi to stop being the parchi that
was signed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.dynamo.serde import SerdeError, dumps, loads
from aadesh_core.domain import Citation, InvocationLifecycle, InvokedStage, SourceState
from aadesh_core.domain.enums import AcknowledgementMethod, ParchiState, StandingOrderAction
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack.tokens import AcknowledgementToken, TokenState
from aadesh_core.standing_order.models import StandingOrderActionClause

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def parchi(**over) -> Parchi:
    return Parchi(
        **{
            "parchi_id": "parchi-001",
            "site_id": "example-piling-site",
            "worker_id": "worker-001",
            "state": ParchiState.PENDING_ACK,
            "created_at": NOW,
            "stage": None,
            "order_sha256": "a" * 64,
            "reading": None,
            "obligation_ids": ("ob-1", "ob-2"),
            "entitlement_refs": (),
            "readiness_checklist": ("Welfare board registration number",),
            "displaced_worker_days": 1,
            **over,
        }
    )


def test_round_trip_preserves_every_field() -> None:
    original = parchi()
    restored = loads(dumps(original), Parchi)
    assert restored == original


def test_round_trip_preserves_optional_none_versus_absent() -> None:
    """`issued_at=None` and `issued_at` missing are different records. Both must survive."""
    original = parchi(acknowledged_at=None, acknowledged_by=None)
    restored = loads(dumps(original), Parchi)
    assert restored.acknowledged_at is None
    assert restored.acknowledged_by is None


def test_tuple_order_is_preserved() -> None:
    """Obligation order is part of the record; a set would reorder it."""
    original = parchi(obligation_ids=("ob-3", "ob-1", "ob-2"))
    restored = loads(dumps(original), Parchi)
    assert restored.obligation_ids == ("ob-3", "ob-1", "ob-2")


def test_enums_round_trip_as_enums_not_strings() -> None:
    restored = loads(dumps(parchi()), Parchi)
    assert isinstance(restored.state, ParchiState)


def test_an_optional_field_holding_a_value_round_trips_as_that_type() -> None:
    """Every `X | None` slot the tests above leave as None is where a decoder bug hides.

    `Parchi.stage` is annotated `InvokedStage | None`, and under PEP 604 the runtime origin of
    that annotation is `types.UnionType` -- not `typing.Union`. A decoder that only tests
    `origin is Union` never unwraps it, falls through to its `isinstance` tail, and hands back
    the raw nested dict; an Optional `datetime` comes back as an ISO string. The tests above
    pass either way, because `stage` is None and the only Optional slots they populate hold
    plain strings. A parchi that has actually been issued carries a real stage and real
    timestamps, so this test has to put real values in the Optional slots.
    """
    stage = InvokedStage(
        stage=3,
        order_doc_id="the-order",
        order_sha256="a" * 64,
        invoked_at=NOW,
        lifecycle=InvocationLifecycle.ACTIVE,
        citation=Citation(source_doc="the-order", page=2, quote="verbatim", source_hash=None),
        source_state=SourceState.VERIFIED,
    )
    original = parchi(
        stage=stage,
        issued_at=NOW,
        acknowledgement_method=AcknowledgementMethod.QR_CONFIRMED,
    )
    restored = loads(dumps(original), Parchi)

    assert isinstance(restored.stage, InvokedStage), "an Optional dataclass came back as a dict"
    assert isinstance(restored.issued_at, datetime), "an Optional datetime came back as a string"
    assert isinstance(restored.acknowledgement_method, AcknowledgementMethod)
    assert restored == original


def test_a_str_annotated_field_holding_an_enum_round_trips_as_the_enum() -> None:
    """`AcknowledgementToken.state` is annotated `str` but its default is `TokenState.ACTIVE`,
    so it holds an enum at runtime. Reconstructing it as a bare string would make
    `token.state is TokenState.CONSUMED` false -- and a consumed token read back from DynamoDB
    looking unspent is the exact failure the compare-and-set in Task 6 exists to prevent."""
    token = AcknowledgementToken(
        token_hash="a" * 64,
        parchi_id="parchi-001",
        worker_id="worker-001",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=24),
        state=TokenState.CONSUMED,
    )
    restored = loads(dumps(token), AcknowledgementToken)
    assert restored.state is TokenState.CONSUMED
    assert restored == token


def test_a_frozen_mapping_round_trips() -> None:
    """`StandingOrderActionClause.parameters` is annotated `dict[str, Any]`, but `__post_init__`
    freezes it into a `frozendict`. That is a dict subclass, so without a mapping branch in the
    encoder every standing order fails to serialise at all."""
    clause = StandingOrderActionClause(
        action=StandingOrderAction.ISSUE_HALT,
        parameters={"halt_duration_hours": 8, "nested": {"ceiling_metres": 3}},
    )
    restored = loads(dumps(clause), StandingOrderActionClause)
    assert restored == clause
    assert restored.parameters["halt_duration_hours"] == 8
    assert restored.parameters["nested"]["ceiling_metres"] == 3


def test_an_unknown_field_is_refused_not_ignored() -> None:
    """A field written by a newer build must not be silently discarded by an older one."""
    payload = dumps(parchi())
    payload["a_field_from_the_future"] = 1
    with pytest.raises(SerdeError, match="a_field_from_the_future"):
        loads(payload, Parchi)


def test_a_missing_field_is_refused_not_defaulted() -> None:
    payload = dumps(parchi())
    del payload["content_hash"]
    with pytest.raises(SerdeError, match="content_hash"):
        loads(payload, Parchi)


def test_a_naive_datetime_is_refused() -> None:
    with pytest.raises(SerdeError, match="timezone-aware"):
        dumps(parchi(created_at=datetime(2026, 10, 9, 9, 0)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_dynamo_serde.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.store.dynamo'`

- [ ] **Step 3: Write the serde**

`loads` is driven by the type hints rather than a hand-written field table, so it cannot fall out of step with the dataclass. `dataclasses.fields` plus `typing.get_type_hints` resolve `from __future__ import annotations` correctly.

```python
# services/aadesh_adapters/store/dynamo/serde.py
"""Round-trip serialisation for the records DynamoDB holds.

Written by hand rather than with `dataclasses.asdict` for three reasons, each of which is a
way a stored record stops being the record that was signed:

  * `asdict` renders a StrEnum as a bare string with nothing to validate it against;
  * it cannot distinguish an absent key from a null one;
  * it silently ignores a field added to the dataclass later, so a newer writer and an older
    reader disagree without either noticing.

`loads` reconstructs from the type hints, and refuses a payload whose key set does not match
the dataclass exactly. Adding a field to `Parchi` therefore breaks loudly here, which is the
behaviour we want from the one place evidence records cross a durability boundary.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


class SerdeError(ValueError):
    """A record could not be serialised or reconstructed without loss."""


def _encode(value: Any) -> Any:
    # Enum is checked BEFORE str/int, deliberately. A StrEnum member IS a str and an IntEnum
    # member IS an int, so the scalar branch below would return the member itself rather than
    # its value, leaving the round trip dependent on the enum's own string behaviour.
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SerdeError(
                "Refusing to serialise a naive datetime. Every timestamp on a stored record "
                "is compared against a timezone-aware clock."
            )
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_encode(v) for v in value]
    if isinstance(value, Mapping):
        # frozendict is a dict subclass, so this covers StandingOrderActionClause.parameters.
        return {str(k): _encode(v) for k, v in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    raise SerdeError(f"No codec for {type(value).__name__}.")


def _decode(value: Any, hint: Any) -> Any:
    if hint is Any or hint is None:
        return value
    origin = get_origin(hint)

    # BOTH spellings of an optional field have to be handled, and the PEP 604 one is the
    # common case: every `X | None` in this codebase resolves to `types.UnionType`, whose
    # origin is NOT `typing.Union`. A check for `typing.Union` alone silently skips the whole
    # branch and falls through to the `isinstance` tail, which returns the raw payload -- so
    # `Parchi.stage` comes back as a dict and `issued_at` comes back as a str. The fixtures in
    # this task's test module leave those slots None, which is exactly why a decoder carrying
    # only the `typing.Union` check passes all of them.
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(hint) if a is not type(None)]
        if value is None:
            return None
        if len(args) != 1:
            raise SerdeError(f"Cannot decode {value!r} into {hint}.")
        return _decode(value, args[0])

    if origin in (tuple, list):
        args = get_args(hint)
        item_hint = args[0] if args else Any
        decoded = [_decode(v, item_hint) for v in value]
        return tuple(decoded) if origin is tuple else decoded

    if origin in (dict, Mapping):
        args = get_args(hint)
        value_hint = args[1] if len(args) == 2 else Any
        return {k: _decode(v, value_hint) for k, v in value.items()}

    if hint is datetime:
        if not isinstance(value, str):
            raise SerdeError(f"Expected an ISO string for datetime, got {type(value).__name__}.")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise SerdeError(f"{value!r} is not timezone-aware.")
        return parsed

    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(value)

    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        if not isinstance(value, Mapping):
            raise SerdeError(f"Expected a mapping for {hint.__name__}, got {type(value).__name__}.")
        return _decode_dataclass(value, hint)

    if isinstance(value, hint) if isinstance(hint, type) else True:
        return value
    raise SerdeError(f"Cannot decode {value!r} into {hint}.")


def _decode_dataclass[T](payload: Mapping[str, Any], hint: type[T]) -> T:
    fields = dataclasses.fields(hint)
    hints = get_type_hints(hint)
    expected = {f.name for f in fields}
    provided = set(payload)

    unknown = provided - expected
    if unknown:
        raise SerdeError(
            f"{hint.__name__} payload carries unknown field(s) {sorted(unknown)}. A field this "
            f"build does not know about must not be discarded silently."
        )
    missing = expected - provided
    if missing:
        raise SerdeError(
            f"{hint.__name__} payload is missing field(s) {sorted(missing)}. Defaulting them "
            f"would reconstruct a record that was never written."
        )

    # A field annotated `str` whose default is an Enum member holds an enum at runtime.
    # `AcknowledgementToken.state` is exactly that: `state: str = TokenState.ACTIVE`. Decoding
    # it as a bare string would make `token.state is TokenState.CONSUMED` false, so a consumed
    # token read back from DynamoDB would look unspent to any identity check.
    enum_defaults = {
        f.name: type(f.default)
        for f in fields
        if f.default is not dataclasses.MISSING and isinstance(f.default, Enum)
    }

    kwargs: dict[str, Any] = {}
    for name in expected:
        raw = payload[name]
        if name in enum_defaults and hints[name] is str:
            kwargs[name] = enum_defaults[name](raw)
        else:
            kwargs[name] = _decode(raw, hints[name])
    return hint(**kwargs)


def dumps(value: Any) -> dict[str, Any]:
    """Serialise a record into a JSON-shaped dict, refusing anything lossy."""
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise SerdeError(f"dumps expects a dataclass, got {type(value).__name__}.")
    return encoded


def loads[T](payload: Mapping[str, Any], hint: type[T]) -> T:
    """Reconstruct a record, refusing an unknown or missing field."""
    return _decode_dataclass(payload, hint)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_dynamo_serde.py -v`
Expected: PASS (10 tests)

If `test_round_trip_preserves_every_field` fails on a field type with no codec, add the codec to `_encode`/`_decode` — do **not** widen the `Any` fallback to swallow it. For reading failures: `Parchi.stage` is an `InvokedStage` (`services/aadesh_core/domain/models.py:92`), whose nested `Citation` (line 37) is another dataclass and whose `lifecycle` is the StrEnum `InvocationLifecycle` (`ACTIVE`/`REVOKED`) — so it round-trips through the dataclass branch, the nested dataclass branch and the enum branch in turn. `Parchi` has no `__post_init__` at all, which is why `test_a_naive_datetime_is_refused` exercises `_encode`'s own guard rather than a constructor check.

`test_an_optional_field_holding_a_value_round_trips_as_that_type` is the one to watch. If you find yourself wanting to drop it because "the other tests already cover the round trip", that is the bug talking: every other fixture passes `stage=None`, so without this test the entire `X | None` branch of `_decode` is unexercised and a decoder that never unwraps PEP 604 unions passes the whole module.

- [ ] **Step 5: Confirm the whole offline suite still passes**

Run: `make test`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/__init__.py \
        services/aadesh_adapters/store/dynamo/serde.py tests/unit/test_dynamo_serde.py
git commit -m "feat(adapters): add a loud round-trip serde for stored evidence records"
```

---

### Task 4: DynamoDB client, table names, and the LocalStack harness

One module owns boto3 for the store, so the endpoint override lives in a single place and every adapter is testable against LocalStack by setting one variable.

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/client.py`
- Create: `docker-compose.yml`
- Create: `tests/contract/conftest.py`
- Modify: `Makefile`
- Test: `tests/unit/test_dynamo_client.py`

**Interfaces:**
- Produces: `TABLES` (a frozen mapping of logical name → physical name), `dynamo_resource()`, `dynamo_client()`, `s3_client()`, `endpoint_url()`, `conditional_write()` — a context manager translating a lost conditional write into `ConditionalCheckFailed` — and that `ConditionalCheckFailed` itself, the normalised exception the adapters translate from `ClientError`.
- Produces for tests: a `dynamo_tables` fixture (session-scoped, `integration`-marked) that creates the six tables and yields the physical names.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dynamo_client.py
"""Table names and endpoint resolution, with no AWS call and no boto3 required."""

from __future__ import annotations

import pytest

from aadesh_adapters.store.dynamo.client import (
    TABLES,
    ConditionalCheckFailed,
    conditional_write,
    endpoint_url,
)


class _LostRace(Exception):
    """Stands in for botocore's `ClientError` without importing botocore."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def test_table_names_are_the_documented_ones() -> None:
    assert TABLES["parchis"] == "aadesh-parchis"
    assert TABLES["operational"] == "aadesh-operational"
    assert TABLES["standing_orders"] == "aadesh-standing-orders"
    assert TABLES["trigger_runs"] == "aadesh-trigger-runs"
    assert TABLES["readings"] == "aadesh-readings"
    assert TABLES["sites"] == "aadesh-sites"


def test_endpoint_url_is_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    assert endpoint_url() is None, "a blank override must mean real AWS, not a broken URL"


def test_endpoint_url_is_honoured_when_set(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    assert endpoint_url() == "http://localhost:4566"


def test_a_lost_conditional_write_becomes_conditional_check_failed() -> None:
    with pytest.raises(ConditionalCheckFailed):
        with conditional_write():
            raise _LostRace("ConditionalCheckFailedException")


def test_any_other_client_error_is_not_swallowed() -> None:
    """Translating every error would turn a throttle into "already exists", and a redelivered
    trigger would then skip work it never did instead of retrying it."""
    with pytest.raises(_LostRace):
        with conditional_write():
            raise _LostRace("ProvisionedThroughputExceededException")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_dynamo_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.store.dynamo.client'`

- [ ] **Step 3: Write the client module**

`boto3` is imported **inside** the functions, matching `explain/bedrock.py`, so this module imports cleanly with only the `dev` extra installed.

```python
# services/aadesh_adapters/store/dynamo/client.py
"""The one place the store touches boto3.

boto3 is imported lazily, inside the functions, for the same reason `explain/bedrock.py` does
it: it lives in the opt-in `aws` extra, and `make test` must run on a machine that has never
installed it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from types import MappingProxyType
from typing import Any

TABLES = MappingProxyType(
    {
        "parchis": "aadesh-parchis",
        "operational": "aadesh-operational",
        "standing_orders": "aadesh-standing-orders",
        "trigger_runs": "aadesh-trigger-runs",
        "readings": "aadesh-readings",
        "sites": "aadesh-sites",
    }
)


class ConditionalCheckFailed(RuntimeError):
    """A conditional write lost its race.

    Adapters translate boto3's `ConditionalCheckFailedException` into this so no caller has to
    catch a `ClientError` and inspect a string to know that something already existed.
    """


class DynamoUnavailable(RuntimeError):
    """boto3 is not installed, or the table is unreachable. Never silently degraded."""


@contextmanager
def conditional_write() -> Iterator[None]:
    """Translate a lost conditional write into `ConditionalCheckFailed`.

    Every conditional `put_item` in this package wraps its call in this. boto3 signals a lost
    race by raising a `ClientError` whose `Error.Code` is the string
    `"ConditionalCheckFailedException"`; letting that escape would force every adapter -- and
    every caller of every adapter -- to know the string exists.

    It matches on the exception's `.response` attribute rather than importing `botocore`, so
    this module keeps importing cleanly without the aws extra, which is what lets
    `test_dynamo_client.py` run on a machine that has never installed boto3.
    """
    try:
        yield
    except Exception as exc:
        code = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code", "")
        if code != "ConditionalCheckFailedException":
            raise
        raise ConditionalCheckFailed(f"conditional write lost its race: {code}") from exc


def endpoint_url() -> str | None:
    """LocalStack override. Unset or blank means real AWS."""
    value = os.environ.get("AWS_ENDPOINT_URL", "").strip()
    return value or None


def _boto3() -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - the default path never reaches here
        raise DynamoUnavailable(
            "boto3 is not installed. Install the aws extra: uv pip install -e '.[aws]'"
        ) from exc
    return boto3


def dynamo_resource() -> Any:
    return _boto3().resource(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", "ap-south-1"),
        endpoint_url=endpoint_url(),
    )


def dynamo_client() -> Any:
    return _boto3().client(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", "ap-south-1"),
        endpoint_url=endpoint_url(),
    )


def s3_client() -> Any:
    """The S3 half of the same boundary.

    `S3Corpus` takes an injected client rather than building one, so that the corpus rules stay
    testable without AWS. This function is what its one production caller injects.
    """
    return _boto3().client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "ap-south-1"),
        endpoint_url=endpoint_url(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_dynamo_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the LocalStack compose file**

```yaml
# docker-compose.yml
# Opt-in only. `make test` never touches this; `make test-integration` does.
services:
  localstack:
    image: localstack/localstack:3.8
    ports:
      - "4566:4566"
    environment:
      SERVICES: dynamodb,s3,ssm,stepfunctions
      DEBUG: "0"
    volumes:
      - "./.localstack:/var/lib/localstack"
```

Add `.localstack/` to `.gitignore`.

- [ ] **Step 6: Write the contract fixtures**

```python
# tests/contract/conftest.py
"""Fixtures shared by the adapter contract suites.

Nothing here runs during `make test`. The default run deselects the `integration` marker
(`-m "not integration and not requires_index"`), so an integration-parametrised case is never
collected and the fixtures it requests are never set up -- which is what keeps the default
path free of Docker and AWS.
"""

from __future__ import annotations

import os

import pytest

from aadesh_adapters.store.dynamo.client import TABLES

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")

_PARCHI_TABLE = {
    "TableName": TABLES["parchis"],
    "KeySchema": [{"AttributeName": "parchi_id", "KeyType": "HASH"}],
    "AttributeDefinitions": [
        {"AttributeName": "parchi_id", "AttributeType": "S"},
        {"AttributeName": "site_id", "AttributeType": "S"},
        {"AttributeName": "worker_id", "AttributeType": "S"},
        {"AttributeName": "idempotency_key", "AttributeType": "S"},
    ],
    "BillingMode": "PAY_PER_REQUEST",
    "GlobalSecondaryIndexes": [
        {
            "IndexName": f"{name}-index",
            "KeySchema": [{"AttributeName": name, "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        }
        for name in ("site_id", "worker_id", "idempotency_key")
    ],
}

_SIMPLE_TABLES = {
    TABLES["operational"]: "pk",
    TABLES["standing_orders"]: "standing_order_id",
    TABLES["trigger_runs"]: "fingerprint",
    TABLES["sites"]: "site_id",
}


@pytest.fixture(scope="session")
def dynamo_tables():
    """Create the tables against LocalStack once per session, and pin the endpoint.

    The pin is here rather than in an autouse fixture on purpose. `dynamo_resource()` reads
    `AWS_ENDPOINT_URL` at call time and treats *unset* as *real AWS*, so without a pin someone
    typing `uv run pytest -m integration` instead of `make test-integration` would point real
    adapters at whatever account their credentials name. An autouse fixture would also fire for
    the offline run -- `tests/contract/` already holds `test_aqi_provider_contract.py` -- and
    mutate the environment of a suite that must never touch AWS at all. As a plain fixture it
    runs only when a test asks for it, and every integration fixture depends on it, so pytest
    is guaranteed to pin the endpoint before any adapter is constructed.

    **Every integration fixture must depend on this one**, directly or indirectly. One that
    does not will build its adapter against real AWS.
    """
    previous = os.environ.get("AWS_ENDPOINT_URL")
    os.environ["AWS_ENDPOINT_URL"] = ENDPOINT

    boto3 = pytest.importorskip("boto3")
    client = boto3.client(
        "dynamodb", region_name="ap-south-1", endpoint_url=ENDPOINT
    )
    existing = set(client.list_tables()["TableNames"])

    if TABLES["parchis"] not in existing:
        client.create_table(**_PARCHI_TABLE)
    for name, key in _SIMPLE_TABLES.items():
        if name not in existing:
            client.create_table(
                TableName=name,
                KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
    for name in (*_SIMPLE_TABLES, TABLES["parchis"]):
        client.get_waiter("table_exists").wait(TableName=name)

    try:
        yield TABLES
    finally:
        if previous is None:
            os.environ.pop("AWS_ENDPOINT_URL", None)
        else:
            os.environ["AWS_ENDPOINT_URL"] = previous
```

> **Reading the `Expected: FAIL` lines in Tasks 5–9.** Those steps run with `-m integration`,
> and the DynamoDB fixture resolves `dynamo_tables` *before* it imports the adapter under
> test. With LocalStack up, the failure is the stated `ModuleNotFoundError`. With it down, the
> fixture fails first with a botocore endpoint-connection error — that is the harness telling
> you Docker is not running, not the test failing for some other reason. `make localstack`
> starts it.

- [ ] **Step 7: Add the LocalStack target to the existing integration target**

`test-integration` **already exists** in the `Makefile` (line ~35) as `$(PY) -m pytest -m integration`. Do not add a second definition — make would print `overriding recipe for target 'test-integration'` and silently keep the last one. Add `localstack` to the existing `.PHONY` list (line ~17) and leave the target's recipe alone: the endpoint is now pinned by the `dynamo_tables` fixture, so an environment prefix on the command would be redundant, and `VAR=value cmd` is not valid PowerShell anyway. The default `test` path is untouched.

```make
localstack: ## Start LocalStack in Docker for the integration suites
	docker compose up -d localstack
	@echo "LocalStack on http://localhost:4566. Run: make test-integration"
```

- [ ] **Step 8: Verify the offline default is unaffected**

Run: `make test`
Expected: PASS. `tests/contract/conftest.py` is imported by the existing
`test_aqi_provider_contract.py`, but the `dynamo_tables` fixture is requested by nothing in the
offline run, so no table is created and `AWS_ENDPOINT_URL` is never set.

- [ ] **Step 9: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/client.py docker-compose.yml \
        tests/contract/conftest.py tests/unit/test_dynamo_client.py Makefile .gitignore
git commit -m "feat(adapters): add the DynamoDB client boundary and a LocalStack harness"
```

---

### Task 5: `DynamoParchiStore`

Implements `ParchiAckStore`, which extends `ParchiStore`. `save` must refuse overwriting a `SEALED` parchi and `save_new` must be an atomic conditional create — the two behaviours `InMemoryParchiStore` guards with a lock and `save_new`'s docstring calls out as "the point where check-then-insert becomes a single step."

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/parchi.py`
- Test: `tests/contract/test_parchi_store_contract.py`

**Interfaces:**
- Consumes: `TABLES`, `dynamo_resource`, `ConditionalCheckFailed` from Task 4; `dumps`, `loads` from Task 3.
- Produces: `DynamoParchiStore()` satisfying `ParchiAckStore`.

- [ ] **Step 1: Write the contract suite, parametrised over both adapters**

Follow the existing convention in `tests/contract/test_aqi_provider_contract.py` — an `ADAPTERS` list plus `request.getfixturevalue`. The DynamoDB entry carries the `integration` mark so `make test` runs the memory half only.

```python
# tests/contract/test_parchi_store_contract.py
"""One suite, two adapters. The DynamoDB store is held to the in-memory store's behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_core.domain.enums import ParchiState
from aadesh_core.errors import DuplicateIdempotencyKey, IllegalParchiTransition
from aadesh_core.parchi import Parchi
from aadesh_core.ports.parchi_ack import ParchiAckStore

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
def memory_parchi_store():
    return InMemoryParchiStore()


@pytest.fixture
def dynamo_parchi_store(dynamo_tables):
    from aadesh_adapters.store.dynamo.parchi import DynamoParchiStore

    return DynamoParchiStore()


ADAPTERS = [
    "memory_parchi_store",
    pytest.param("dynamo_parchi_store", marks=pytest.mark.integration),
]


def parchi(**over) -> Parchi:
    return Parchi(
        **{
            "parchi_id": "parchi-001",
            "site_id": "example-piling-site",
            "worker_id": "worker-001",
            "state": ParchiState.PENDING_ACK,
            "created_at": NOW,
            "stage": None,
            "order_sha256": "a" * 64,
            "reading": None,
            "obligation_ids": ("ob-1",),
            "entitlement_refs": (),
            "readiness_checklist": (),
            "displaced_worker_days": 1,
            "idempotency_key": "fp-1:worker-001",
            **over,
        }
    )


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), ParchiAckStore)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_get_returns_none_for_unknown(adapter_name, request):
    assert request.getfixturevalue(adapter_name).get("nope") is None


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_round_trips_a_parchi(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.save_new(parchi())
    assert store.get("parchi-001") == parchi()


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_save_new_refuses_a_duplicate_idempotency_key(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.save_new(parchi())
    with pytest.raises(DuplicateIdempotencyKey):
        store.save_new(parchi(parchi_id="parchi-002"))


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_find_by_idempotency_key_returns_the_original(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.save_new(parchi())
    found = store.find_by_idempotency_key("fp-1:worker-001")
    assert found is not None
    assert found.parchi_id == "parchi-001"


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_save_refuses_to_overwrite_a_sealed_parchi(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.save_new(parchi(state=ParchiState.SEALED))
    with pytest.raises(IllegalParchiTransition):
        store.save(parchi(state=ParchiState.SEALED, order_sha256="b" * 64))


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_for_site_and_for_worker_filter(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.save_new(parchi())
    store.save_new(parchi(parchi_id="parchi-002", worker_id="worker-002", idempotency_key=None))
    assert len(store.for_site("example-piling-site")) == 2
    assert len(store.for_worker("worker-002")) == 1
    assert store.for_worker("worker-999") == ()
```

- [ ] **Step 2: Run to verify the memory half passes and the dynamo half errors**

Run: `uv run pytest tests/contract/test_parchi_store_contract.py -v -m "not integration"`
Expected: PASS for the memory param; the dynamo param is deselected, so this run is green.

Run: `uv run pytest tests/contract/test_parchi_store_contract.py -v -m integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.store.dynamo.parchi'`

- [ ] **Step 3: Implement the store**

```python
# services/aadesh_adapters/store/dynamo/parchi.py
"""DynamoDB-backed Parchi persistence.

Two conditional writes carry the whole contract:

  * `save_new` uses `attribute_not_exists(idempotency_key)` on a dedicated guard item, so two
    concurrent creations for one displaced worker cannot both succeed. A read-then-write would
    be one scheduler tick away from exactly that.
  * `save` uses `attribute_not_exists(sealed)` so a sealed record can never be overwritten.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from aadesh_core.domain.enums import ParchiState
from aadesh_core.errors import DuplicateIdempotencyKey, IllegalParchiTransition
from aadesh_core.parchi import Parchi

from aadesh_adapters.store.dynamo.client import (
    TABLES,
    ConditionalCheckFailed,
    conditional_write,
    dynamo_resource,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads

#: Exactly the fields `loads` will accept, derived from the dataclass rather than retyped.
_PARCHI_FIELDS = frozenset(f.name for f in fields(Parchi))


class DynamoParchiStore:
    def __init__(self, *, table_name: str | None = None) -> None:
        self._table_name = table_name or TABLES["parchis"]
        self._resource = None

    @property
    def _table(self) -> Any:
        if self._resource is None:
            self._resource = dynamo_resource()
        return self._resource.Table(self._table_name)

    def _item(self, parchi: Parchi) -> dict[str, Any]:
        item = dumps(parchi)
        item["sealed"] = parchi.state is ParchiState.SEALED
        if parchi.idempotency_key is None:
            # Remove the key entirely rather than storing a NULL. DynamoDB treats a typed NULL
            # as present, so `attribute_not_exists(idempotency_key)` would be false for every
            # keyless parchi -- they would all look like they already held a key. It would also
            # make the sparse GSI dense, indexing records that have nothing to look up.
            item.pop("idempotency_key")
        return item

    def _from_item(self, item: dict[str, Any]) -> Parchi:
        payload = {k: v for k, v in item.items() if k in _PARCHI_FIELDS}
        # Undo the drop above: `loads` requires every declared field to be present, and a
        # missing key means None, not "unknown".
        payload.setdefault("idempotency_key", None)
        return loads(payload, Parchi)

    def save(self, parchi: Parchi) -> None:
        try:
            with conditional_write():
                self._table.put_item(
                    Item=self._item(parchi),
                    ConditionExpression="attribute_not_exists(parchi_id) OR sealed = :false",
                    ExpressionAttributeValues={":false": False},
                )
        except ConditionalCheckFailed:
            raise IllegalParchiTransition(
                f"Parchi {parchi.parchi_id} is sealed and cannot be overwritten. "
                f"Sealed records are append-only evidence."
            ) from None

    def save_new(self, parchi: Parchi) -> None:
        key = parchi.idempotency_key
        condition = (
            "attribute_not_exists(idempotency_key)"
            if key is not None
            else "attribute_not_exists(parchi_id)"
        )
        try:
            with conditional_write():
                self._table.put_item(Item=self._item(parchi), ConditionExpression=condition)
        except ConditionalCheckFailed:
            if key is not None:
                raise DuplicateIdempotencyKey(key) from None
            raise

    def get(self, parchi_id: str) -> Parchi | None:
        response = self._table.get_item(Key={"parchi_id": parchi_id})
        item = response.get("Item")
        return self._from_item(item) if item else None

    def _by_index(self, index: str, value: str) -> tuple[Parchi, ...]:
        response = self._table.query(
            IndexName=f"{index}-index",
            KeyConditionExpression="#k = :v",
            ExpressionAttributeNames={"#k": index},
            ExpressionAttributeValues={":v": value},
        )
        return tuple(self._from_item(i) for i in response.get("Items", ()))

    def for_site(self, site_id: str) -> tuple[Parchi, ...]:
        return self._by_index("site_id", site_id)

    def for_worker(self, worker_id: str) -> tuple[Parchi, ...]:
        return self._by_index("worker_id", worker_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> Parchi | None:
        found = self._by_index("idempotency_key", idempotency_key)
        return found[0] if found else None
```

`_item` writes the serde fields plus a derived `sealed` flag, which is what the `save` condition tests. `_from_item` filters the item back down to `_PARCHI_FIELDS` before handing it to `loads`, because `loads` refuses any key the dataclass does not declare — and `sealed` is deliberately not a `Parchi` field. Filtering here rather than teaching the serde to ignore extras is the point: an unexpected key must fail loudly, and this is the one known, derived addition.

- [ ] **Step 4: Run the memory half**

Run: `uv run pytest tests/contract/test_parchi_store_contract.py -v -m "not integration"`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the DynamoDB half against LocalStack**

Requires `docker compose up -d localstack` (Task 4). If the Docker daemon is not running, start Docker Desktop first — this is the documented prerequisite.

Run: `uv run pytest tests/contract/test_parchi_store_contract.py -v -m integration`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/parchi.py \
        tests/contract/test_parchi_store_contract.py
git commit -m "feat(adapters): add DynamoParchiStore with conditional create and sealed-write refusal"
```

---

### Task 6: `DynamoAcknowledgementTokenStore`

The compare-and-set. `InMemoryAcknowledgementTokenStore.consume` checks `UNKNOWN`, then `CONSUMED`, then `EXPIRED`, and raises `TokenRejected` with a distinct `reason` for each — the reason is for the audit log and never for the response. The DynamoDB adapter must reproduce that ordering, because a conditional write alone would collapse all three into one failure.

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/ack.py`
- Test: `tests/contract/test_ack_token_store_contract.py`

**Interfaces:**
- Consumes: `TABLES`, `dynamo_resource`, `ConditionalCheckFailed` (Task 4); `dumps`/`loads` (Task 3); `AcknowledgementToken`, `TokenState` from `aadesh_core.parchi_ack.tokens`.
- Produces: `DynamoAcknowledgementTokenStore()`.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/contract/test_ack_token_store_contract.py
"""Consume is a compare-and-set. The loser must lose, and must lose loudly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.memory_ack import InMemoryAcknowledgementTokenStore
from aadesh_core.errors import TokenRejected, TokenRejectionReason
from aadesh_core.parchi_ack.tokens import AcknowledgementToken, TokenState
from aadesh_core.ports.parchi_ack import AcknowledgementTokenStore

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
TTL = timedelta(hours=24)
HASH = "a" * 64


def token(*, state=TokenState.ACTIVE, expires_at=NOW + TTL) -> AcknowledgementToken:
    return AcknowledgementToken(
        token_hash=HASH,
        parchi_id="parchi-001",
        worker_id="worker-001",
        issued_at=NOW,
        expires_at=expires_at,
        state=state,
    )


@pytest.fixture
def memory_token_store():
    return InMemoryAcknowledgementTokenStore()


@pytest.fixture
def dynamo_token_store(dynamo_tables):
    from aadesh_adapters.store.dynamo.ack import DynamoAcknowledgementTokenStore

    return DynamoAcknowledgementTokenStore()


ADAPTERS = [
    "memory_token_store",
    pytest.param("dynamo_token_store", marks=pytest.mark.integration),
]


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), AcknowledgementTokenStore)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_get_returns_none_for_unknown(adapter_name, request):
    assert request.getfixturevalue(adapter_name).get("b" * 64) is None


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_round_trips_a_token(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.put(token())
    assert store.get(HASH) == token()


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_consume_marks_the_token_consumed(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.put(token())
    consumed = store.consume(HASH, at=NOW, event_id="evt-1")
    assert consumed.state is TokenState.CONSUMED
    assert consumed.consumed_event_id == "evt-1"
    # Re-read through the store, not the returned object.
    assert store.get(HASH).state is TokenState.CONSUMED


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_second_consume_is_rejected_as_consumed(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.put(token())
    store.consume(HASH, at=NOW, event_id="evt-1")
    with pytest.raises(TokenRejected) as excinfo:
        store.consume(HASH, at=NOW, event_id="evt-2")
    assert excinfo.value.reason is TokenRejectionReason.CONSUMED


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_unknown_token_is_rejected_as_unknown_not_consumed(adapter_name, request):
    """The three reasons are distinguishable in the audit log even though the caller's
    message is identical. Collapsing them would lose that."""
    store = request.getfixturevalue(adapter_name)
    with pytest.raises(TokenRejected) as excinfo:
        store.consume("c" * 64, at=NOW, event_id="evt-1")
    assert excinfo.value.reason is TokenRejectionReason.UNKNOWN


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_expired_token_is_rejected_as_expired(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.put(token(expires_at=NOW - timedelta(minutes=1)))
    with pytest.raises(TokenRejected) as excinfo:
        store.consume(HASH, at=NOW, event_id="evt-1")
    assert excinfo.value.reason is TokenRejectionReason.EXPIRED
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/contract/test_ack_token_store_contract.py -m integration -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.store.dynamo.ack'`

- [ ] **Step 3: Implement it**

Read the token first so the three rejection reasons stay distinguishable, then make the write conditional on the token still being `ACTIVE`. The read is not the guard — the condition is. If two callers both read `ACTIVE`, exactly one write succeeds.

```python
# services/aadesh_adapters/store/dynamo/ack.py
"""DynamoDB acknowledgement-token storage. Holds hashes, never raw tokens.

`consume` reads first, so UNKNOWN / CONSUMED / EXPIRED stay three distinct reasons in the
audit log, then writes under a condition that the token is still ACTIVE. The read is for the
reason; the condition is the guard. Two callers that both read ACTIVE are separated by the
conditional write, and the loser raises rather than returning quietly.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from aadesh_core.errors import TokenRejected, TokenRejectionReason
from aadesh_core.parchi_ack.tokens import AcknowledgementToken, TokenState

from aadesh_adapters.store.dynamo.client import (
    TABLES,
    ConditionalCheckFailed,
    conditional_write,
    dynamo_resource,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads

_KIND = "acktoken"


class DynamoAcknowledgementTokenStore:
    def __init__(self, *, table_name: str | None = None) -> None:
        self._table_name = table_name or TABLES["operational"]
        self._resource = None

    @property
    def _table(self) -> Any:
        if self._resource is None:
            self._resource = dynamo_resource()
        return self._resource.Table(self._table_name)

    @staticmethod
    def _key(token_hash: str) -> dict[str, str]:
        return {"pk": f"{_KIND}#{token_hash}"}

    def put(self, token: AcknowledgementToken) -> None:
        item = dumps(token)
        item.update(self._key(token.token_hash))
        self._table.put_item(Item=item)

    def get(self, token_hash: str) -> AcknowledgementToken | None:
        response = self._table.get_item(Key=self._key(token_hash))
        item = response.get("Item")
        if not item:
            return None
        return loads({k: v for k, v in item.items() if k != "pk"}, AcknowledgementToken)

    def consume(self, token_hash: str, *, at: datetime, event_id: str) -> AcknowledgementToken:
        current = self.get(token_hash)

        # UNKNOWN is checked first and reads identically to the others to a caller: same
        # exception type, same sentence. Only `reason` differs, and that is for the audit log.
        if current is None:
            raise TokenRejected(TokenRejectionReason.UNKNOWN)
        if current.state is TokenState.CONSUMED:
            raise TokenRejected(TokenRejectionReason.CONSUMED)
        if current.is_expired(at):
            raise TokenRejected(TokenRejectionReason.EXPIRED)

        consumed = replace(
            current,
            state=TokenState.CONSUMED,
            consumed_at=at,
            consumed_event_id=event_id,
        )
        item = dumps(consumed)
        item.update(self._key(token_hash))
        try:
            with conditional_write():
                self._table.put_item(
                    Item=item,
                    ConditionExpression="#state = :active",
                    ExpressionAttributeNames={"#state": "state"},
                    ExpressionAttributeValues={":active": TokenState.ACTIVE.value},
                )
        except ConditionalCheckFailed:
            # Someone consumed it between the read and this write.
            raise TokenRejected(TokenRejectionReason.CONSUMED) from None
        return consumed
```

- [ ] **Step 4: Run both halves**

Run: `uv run pytest tests/contract/test_ack_token_store_contract.py -m "not integration" -v`
Expected: PASS (7 tests)

Run: `uv run pytest tests/contract/test_ack_token_store_contract.py -m integration -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/ack.py \
        tests/contract/test_ack_token_store_contract.py
git commit -m "feat(adapters): add DynamoAcknowledgementTokenStore with a real compare-and-set"
```

---

### Task 7: `DynamoIdempotencyLedger`

The hardest adapter in this phase. The port promises that `compute` runs **at most once per key, ever**, that every later caller receives the first result, and that if `compute` raises the key stays unclaimed so a genuine retry can run. A conditional `PutItem` gives the first two; the third, and the case where the first caller dies mid-compute, need a lease with an expiry and a recovery path.

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/ledger.py`
- Test: `tests/contract/test_idempotency_ledger_contract.py`

**Interfaces:**
- Consumes: `TABLES`, `dynamo_resource`, `ConditionalCheckFailed` (Task 4).
- Produces: `DynamoIdempotencyLedger(*, lease_seconds: int = 30)`.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/contract/test_idempotency_ledger_contract.py
"""execute_once runs compute at most once per key, and never strands a key.

The stranded-key case is the one that matters most and is the easiest to get wrong: if the
first caller dies between claiming the key and recording the result, and nothing recovers the
lease, that worker can never acknowledge. Silently. Only that worker.
"""

from __future__ import annotations

import threading

import pytest

from aadesh_adapters.store.dynamo.client import DynamoUnavailable
from aadesh_adapters.store.memory_ack import InMemoryIdempotencyLedger
from aadesh_core.ports.parchi_ack import IdempotencyLedger


@pytest.fixture
def memory_ledger():
    return InMemoryIdempotencyLedger()


@pytest.fixture
def dynamo_ledger(dynamo_tables):
    from aadesh_adapters.store.dynamo.ledger import DynamoIdempotencyLedger

    return DynamoIdempotencyLedger(lease_seconds=1)


ADAPTERS = [
    "memory_ledger",
    pytest.param("dynamo_ledger", marks=pytest.mark.integration),
]


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), IdempotencyLedger)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_compute_runs_once_and_later_callers_get_the_first_result(adapter_name, request):
    ledger = request.getfixturevalue(adapter_name)
    calls: list[str] = []

    def compute() -> str:
        calls.append("ran")
        return "result-1"

    assert ledger.execute_once(key="k1", compute=compute) == "result-1"
    assert ledger.execute_once(key="k1", compute=compute) == "result-1"
    assert calls == ["ran"], f"compute ran {len(calls)} times for one key"


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_a_raising_compute_leaves_the_key_unclaimed(adapter_name, request):
    """A genuine retry after a transient failure must be able to run."""
    ledger = request.getfixturevalue(adapter_name)

    def boom() -> str:
        raise RuntimeError("transient")

    with pytest.raises(RuntimeError):
        ledger.execute_once(key="k2", compute=boom)

    assert ledger.execute_once(key="k2", compute=lambda: "recovered") == "recovered"


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_an_abandoned_lease_does_not_strand_the_key(adapter_name, request):
    """Simulates the first caller dying mid-compute: claim the key, never record a result,
    let the lease expire, then assert a later caller can complete the work."""
    ledger = request.getfixturevalue(adapter_name)
    if not hasattr(ledger, "abandon"):
        pytest.skip("only the DynamoDB ledger has a lease to abandon")

    ledger.abandon(key="k3")
    assert ledger.execute_once(key="k3", compute=lambda: "after-crash") == "after-crash"


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_a_blank_key_is_refused(adapter_name, request):
    ledger = request.getfixturevalue(adapter_name)
    with pytest.raises(ValueError):
        ledger.execute_once(key="   ", compute=lambda: "x")


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_concurrent_callers_produce_one_execution(adapter_name, request):
    ledger = request.getfixturevalue(adapter_name)
    results: list[str] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        barrier.wait()
        results.append(ledger.execute_once(key="k4", compute=lambda: "once"))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == ["once"] * 3, f"expected three identical results, got {results}"


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_a_structured_result_survives_the_second_caller(adapter_name, request):
    """The recorded result is what every later caller receives, so it must come back equal.

    A mapping is the shape that matters in practice: this ledger records a decision, and a
    decision is a mapping of ids and counts. A string would pass even if the adapter were
    silently lossy, so the assertion has to be on something with structure.
    """
    ledger = request.getfixturevalue(adapter_name)
    first = {"parchi_ids": ["p-1", "p-2"], "count": 2}
    assert ledger.execute_once(key="k6", compute=lambda: first) == first
    again = ledger.execute_once(key="k6", compute=lambda: {"never": "called"})
    assert again == first, "the second caller did not receive the first result"


@pytest.mark.integration
def test_a_live_lease_is_never_double_run(dynamo_ledger):
    """The case the lease exists for: a first caller is still running.

    Both wrong answers are available here and both are silent. Taking the lease away and running
    `compute` ourselves runs the work twice; finding no recorded result and returning one anyway
    invents a result. So the second caller must refuse, loudly, and the first caller's single
    execution must be the only one that ever happened.

    This test is DynamoDB-only because the in-memory ledger has no lease to be live: it detects a
    concurrent claim by holding a lock, so the crash it protects against is not representable
    there. `dynamo_ledger` is built with `lease_seconds=1`, so the refusal arrives in about a
    second rather than after the production thirty.
    """
    entered = threading.Event()
    release = threading.Event()
    runs: list[str] = []

    def slow() -> str:
        runs.append("ran")
        entered.set()
        release.wait(timeout=10)
        return "first"

    first = threading.Thread(target=lambda: dynamo_ledger.execute_once(key="k5", compute=slow))
    first.start()
    assert entered.wait(timeout=10), "the first caller never reached compute"

    with pytest.raises(DynamoUnavailable):
        dynamo_ledger.execute_once(key="k5", compute=lambda: "second")

    release.set()
    first.join(timeout=10)
    assert runs == ["ran"], f"compute ran {len(runs)} times for one key"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/contract/test_idempotency_ledger_contract.py -m "not integration" -v`
Expected: PASS for `memory_ledger` — 6 pass and 1 skips (`test_an_abandoned_lease_does_not_strand_the_key` skips itself, because only the DynamoDB ledger has a lease to abandon). The whole module imports cleanly here: `dynamo_ledger` imports its adapter inside the fixture body, so a missing implementation is not an import error until the integration run.

Run: `uv run pytest tests/contract/test_idempotency_ledger_contract.py -m integration -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.store.dynamo.ledger'`

- [ ] **Step 3: Implement the ledger**

Three states per key, in one item: **CLAIMED** (a lease with `lease_expires_at`), **DONE** (a recorded result), and absent (free). The claim is a conditional write on absence-or-expired-lease. The result write is a conditional write from CLAIMED to DONE. `compute` runs outside any lock; if it raises, the lease is released so a retry is immediate rather than waiting out the lease.

```python
# services/aadesh_adapters/store/dynamo/ledger.py
"""DynamoDB idempotency ledger: compute at most once per key, forever.

The hard part is not the duplicate. It is the crash. If the first caller dies between claiming
the key and recording the result, a naive design strands that key permanently -- and the key is
per (fingerprint, worker), so exactly one worker silently loses the ability to acknowledge.

So a claim is a LEASE, not a flag. It carries an expiry. A later caller may take over a lease
that has expired, which is what makes a crashed first caller recoverable without a sweeper job
and without a human. `compute` is deliberately invoked outside any critical section, and a
raise releases the lease so a genuine retry runs immediately.

**The result goes through JSON.** The in-memory ledger hands back the object `compute` returned;
this one stores it as text, so `T` must be a value JSON can round-trip -- a mapping, a string, a
number, a list, or a nesting of those. A caller passing a dataclass would get the dataclass from
the first call and a string from every later one, which is the kind of divergence the contract
suite exists to catch, so the suite pins a structured result rather than a bare string.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from aadesh_adapters.store.dynamo.client import (
    TABLES,
    ConditionalCheckFailed,
    DynamoUnavailable,
    conditional_write,
    dynamo_resource,
)

T = TypeVar("T")

_KIND = "ledger"
_CLAIMED = "claimed"
_DONE = "done"

_RETRY_SECONDS = 0.05
"""How long to wait before re-reading a key held by another caller. Short enough that the
common case -- a first caller who is still running -- resolves in milliseconds, long enough
that a stalled lease does not become a hot loop."""

_LEASE_SECONDS = 30
"""Default lease. It must exceed the slowest legitimate `compute`, which here is a single
DynamoDB read-modify-write, so thirty seconds is generous by orders of magnitude."""


class DynamoIdempotencyLedger:
    def __init__(self, *, table_name: str | None = None, lease_seconds: int = _LEASE_SECONDS) -> None:
        self._table_name = table_name or TABLES["operational"]
        self._lease = timedelta(seconds=lease_seconds)
        self._resource = None

    @property
    def _table(self) -> Any:
        if self._resource is None:
            self._resource = dynamo_resource()
        return self._resource.Table(self._table_name)

    @staticmethod
    def _key(key: str) -> dict[str, str]:
        return {"pk": f"{_KIND}#{key}"}

    def _read(self, key: str) -> dict[str, Any] | None:
        return self._table.get_item(Key=self._key(key)).get("Item")

    def _claim(self, key: str, now: datetime) -> bool:
        """Take the lease, or take over one that has expired. False means someone else holds it.

        The condition is exactly "no record, or its lease has run out". A record already marked
        `_DONE` carries no `lease_expires_at`, so `lease_expires_at < :now` is false for it and
        it can never be re-claimed -- which is what keeps a completed key's result of record.
        """
        try:
            with conditional_write():
                self._table.put_item(
                    Item={
                        **self._key(key),
                        "status": _CLAIMED,
                        "lease_expires_at": (now + self._lease).isoformat(),
                    },
                    ConditionExpression=(
                        "attribute_not_exists(pk) OR lease_expires_at < :now"
                    ),
                    ExpressionAttributeValues={":now": now.isoformat()},
                )
            return True
        except ConditionalCheckFailed:
            return False

    def _release(self, key: str, now: datetime) -> None:
        """Drop a lease we hold but did not complete, so a retry need not wait it out."""
        try:
            with conditional_write():
                self._table.delete_item(
                    Key=self._key(key),
                    ConditionExpression="#s = :claimed",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":claimed": _CLAIMED},
                )
        except ConditionalCheckFailed:
            pass

    def abandon(self, *, key: str) -> None:
        """Test seam: leave behind exactly the record a crashed caller leaves behind.

        Written through `_claim` so it takes the same code path a real caller takes, but with a
        `now` far enough in the past that the lease it writes is ALREADY OVER. That is the state
        a crashed caller's key reaches once the lease window has passed, and it is the only state
        `execute_once` may take over.

        Claiming with the current time instead would simulate a caller that is merely slow, and
        `execute_once` would -- correctly -- refuse to take over. A test that did that would be
        asserting the wrong behaviour and would fail.
        """
        self._claim(key, datetime.now(UTC) - self._lease - timedelta(seconds=1))

    def execute_once(self, *, key: str, compute: Callable[[], T]) -> T:
        if not key.strip():
            raise ValueError("execute_once requires a non-empty key")

        deadline = datetime.now(UTC) + self._lease
        while True:
            existing = self._read(key)
            if existing is not None and existing.get("status") == _DONE:
                return json.loads(existing["result"])

            if self._claim(key, datetime.now(UTC)):
                break

            if datetime.now(UTC) >= deadline:
                # Someone holds a live lease and has neither released nor completed it. Surface
                # the stall rather than spinning: a hung first caller is an incident, not a
                # queue, and looping forever inside a Lambda would burn the whole timeout.
                raise DynamoUnavailable(
                    f"Key {key!r} is held by another caller and the lease has not expired "
                    f"after {self._lease}. Refusing to risk running the work twice."
                )
            time.sleep(_RETRY_SECONDS)

        try:
            result = compute()
        except Exception:
            self._release(key, datetime.now(UTC))
            raise

        try:
            with conditional_write():
                self._table.put_item(
                    Item={
                        **self._key(key),
                        "status": _DONE,
                        "result": json.dumps(result, default=str),
                    },
                    ConditionExpression="#s = :claimed",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":claimed": _CLAIMED},
                )
        except ConditionalCheckFailed:
            # Our lease expired mid-compute and someone else took over. Their result is the one
            # of record; ours would be a second execution of the same work.
            pass
        return result
```

The `while True` body is a bounded wait, not a spin: `_claim` either succeeds, or the deadline passes and `DynamoUnavailable` is raised. Without the deadline a stalled first caller would hold the key until the Lambda itself timed out, with no line saying why.

`abandon` exists only as a test seam for the crash case, and it writes a *backdated* claim rather than a special-cased flag, so it exercises the same `_claim` path a real crashed caller leaves behind once the lease has run out.

- [ ] **Step 4: Run both halves**

Run: `uv run pytest tests/contract/test_idempotency_ledger_contract.py -m "not integration" -v`
Expected: PASS for the memory adapter (6 passed, 1 skipped).

Run: `uv run pytest tests/contract/test_idempotency_ledger_contract.py -m integration -v`
Expected: PASS (8 tests). `test_an_abandoned_lease_does_not_strand_the_key` needs no waiting —
`abandon` backdates its claim, so `execute_once` takes the lease over on its first attempt.
`test_a_live_lease_is_never_double_run` deliberately does wait, for about a second, because
`dynamo_ledger` is built with `lease_seconds=1`.

- [ ] **Step 5: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/ledger.py \
        tests/contract/test_idempotency_ledger_contract.py
git commit -m "feat(adapters): add DynamoIdempotencyLedger with a recoverable lease"
```

---

### Task 8: `DynamoTaskTokenStore`

Delete-on-read via `DeleteItem` with `ReturnValues=ALL_OLD`, so a retried resume finds nothing.

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/task_token.py`
- Test: `tests/contract/test_task_token_store_contract.py`

**Interfaces:**
- Consumes: `TABLES`, `dynamo_resource` (Task 4); `TaskTokenStore` (Task 1).
- Produces: `DynamoTaskTokenStore()`.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/contract/test_task_token_store_contract.py
"""Delete-on-read. The second pop must return None, not the token again."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.memory_task_token import InMemoryTaskTokenStore
from aadesh_core.ports.task_token import TaskTokenStore

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
def memory_task_tokens():
    return InMemoryTaskTokenStore()


@pytest.fixture
def dynamo_task_tokens(dynamo_tables):
    from aadesh_adapters.store.dynamo.task_token import DynamoTaskTokenStore

    return DynamoTaskTokenStore()


ADAPTERS = [
    "memory_task_tokens",
    pytest.param("dynamo_task_tokens", marks=pytest.mark.integration),
]


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), TaskTokenStore)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_pop_returns_once_then_none(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.put(parchi_id="p1", task_token="tok", expires_at=NOW + timedelta(hours=24))
    assert store.pop(parchi_id="p1") == "tok"
    assert store.pop(parchi_id="p1") is None


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_peek_does_not_remove(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    store.put(parchi_id="p2", task_token="tok", expires_at=NOW + timedelta(hours=24))
    assert store.peek(parchi_id="p2") == "tok"
    assert store.peek(parchi_id="p2") == "tok"


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_unknown_returns_none(adapter_name, request):
    assert request.getfixturevalue(adapter_name).pop(parchi_id="nope") is None


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_naive_expiry_is_refused(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    with pytest.raises(ValueError, match="timezone-aware"):
        store.put(parchi_id="p3", task_token="tok", expires_at=datetime(2026, 10, 10, 9, 0))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/contract/test_task_token_store_contract.py -m integration -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement it**

```python
# services/aadesh_adapters/store/dynamo/task_token.py
"""DynamoDB storage for Step Functions task tokens.

`pop` is a single DeleteItem with ReturnValues=ALL_OLD, which is atomic: two concurrent
resumes cannot both receive the token, because only one delete can return the old value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aadesh_adapters.store.dynamo.client import TABLES, dynamo_resource

_KIND = "tasktoken"


class DynamoTaskTokenStore:
    def __init__(self, *, table_name: str | None = None) -> None:
        self._table_name = table_name or TABLES["operational"]
        self._resource = None

    @property
    def _table(self) -> Any:
        if self._resource is None:
            self._resource = dynamo_resource()
        return self._resource.Table(self._table_name)

    @staticmethod
    def _key(parchi_id: str) -> dict[str, str]:
        return {"pk": f"{_KIND}#{parchi_id}"}

    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None:
        if expires_at.tzinfo is None:
            raise ValueError(
                "TaskTokenStore.put requires a timezone-aware expires_at. A naive datetime "
                "would be compared against the Lambda clock in an unknown zone."
            )
        item: dict[str, Any] = {
            **self._key(parchi_id),
            "task_token": task_token,
            # DynamoDB TTL: the record is reclaimed after the machine's own timeout, so a
            # worker who never scans does not leave a token in the table forever.
            "expires_at": int(expires_at.timestamp()),
            "expires_at_iso": expires_at.isoformat(),
        }
        self._table.put_item(Item=item)

    def pop(self, *, parchi_id: str) -> str | None:
        response = self._table.delete_item(
            Key=self._key(parchi_id),
            ReturnValues="ALL_OLD",
        )
        old = response.get("Attributes")
        return old.get("task_token") if old else None

    def peek(self, *, parchi_id: str) -> str | None:
        item = self._table.get_item(Key=self._key(parchi_id)).get("Item")
        return item.get("task_token") if item else None
```

Two things about TTL belong to phase 2, not here.

**Enable TTL on the `aadesh-operational` table's `expires_at` attribute in the CDK stack.**
That attribute is a *number* (epoch seconds) for a task token and an ISO *string* for an
`AcknowledgementToken`, because `dumps` renders every `datetime` with `isoformat()`. DynamoDB
TTL reclaims numeric values and silently ignores anything else, so it deletes stale task
tokens and leaves ack tokens alone. That is the behaviour we want, but it follows from two
adapters sharing one attribute name — it is not something the TTL configuration states. And
TTL deletion runs hours behind, so `pop` must never assume an expired record is already gone.

**Nothing to add to `_SIMPLE_TABLES` for parity.** It maps a table name to its hash key, and
the fixture's `create_table` call has no room for a TTL specification. The contract suite
deliberately does not test expiry; the port docstring in Task 1 says why.

- [ ] **Step 4: Run both halves**

Run: `uv run pytest tests/contract/test_task_token_store_contract.py -m "not integration" -v`
Expected: PASS (5 tests)

Run: `uv run pytest tests/contract/test_task_token_store_contract.py -m integration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/task_token.py \
        tests/contract/test_task_token_store_contract.py
git commit -m "feat(adapters): add DynamoTaskTokenStore with atomic delete-on-read"
```

---

### Task 9: `DynamoStandingOrderStore` and `DynamoTriggerRunStore`

`TriggerRunStore.claim` is the chokepoint that makes duplicate parchis unrepresentable, and its contract is create-if-absent returning the **existing** run — not raising. A conditional `PutItem` raises on collision, so the adapter must read back and return the winner.

**Files:**
- Create: `services/aadesh_adapters/store/dynamo/standing_order.py`
- Test: `tests/contract/test_standing_order_store_contract.py`

**Interfaces:**
- Consumes: `TABLES`, `dynamo_resource`, `ConditionalCheckFailed` (Task 4); `dumps`/`loads` (Task 3).
- Produces: `DynamoStandingOrderStore()`, `DynamoTriggerRunStore()`.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/contract/test_standing_order_store_contract.py
"""Two stores, one suite each half of which runs against both adapters.

`claim()` returns the existing run. It does not raise, because its caller is a Step Functions
retry that has no way to act on a collision.

Every id this module writes carries a fresh uuid4. The DynamoDB tables are session-scoped and
LocalStack persists between runs, so a fixed `"fp-1"` would be found already present on the
second `make test-integration` and the collision test would pass without ever colliding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aadesh_adapters.store.memory_standing_order import (
    InMemoryStandingOrderStore,
    InMemoryTriggerRunStore,
)
from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import TriggerRun
from aadesh_core.standing_order.ports import StandingOrderStore, TriggerRunStore
from tests.support.builders import standing_order

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def run(*, fingerprint: str | None = None, parchi_ids=("parchi-001",)) -> TriggerRun:
    # parchi_ids defaults to a non-empty tuple on purpose: TriggerRun.__post_init__ raises
    # "a trigger run must carry at least the parchi ids it created" for an empty one.
    return TriggerRun(
        fingerprint=fingerprint or f"fp-{uuid4()}",
        standing_order_id="so-1",
        site_id="example-piling-site",
        stage=3,
        order_doc_id="order-001",
        order_sha256="a" * 64,
        started_at=NOW,
        status=StandingOrderStatus.TRIGGERED,
        parchi_ids=tuple(parchi_ids),
    )


@pytest.fixture
def memory_trigger_runs():
    return InMemoryTriggerRunStore()


@pytest.fixture
def dynamo_trigger_runs(dynamo_tables):
    from aadesh_adapters.store.dynamo.standing_order import DynamoTriggerRunStore

    return DynamoTriggerRunStore()


TRIGGER_RUN_ADAPTERS = [
    "memory_trigger_runs",
    pytest.param("dynamo_trigger_runs", marks=pytest.mark.integration),
]


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), TriggerRunStore)


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_claim_creates_when_absent(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    fresh = run()
    assert store.claim(fresh).fingerprint == fresh.fingerprint
    assert store.get(fresh.fingerprint) is not None


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_claim_returns_the_existing_run_on_collision(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    fingerprint = f"fp-{uuid4()}"
    store.claim(run(fingerprint=fingerprint, parchi_ids=("parchi-001",)))
    second = store.claim(run(fingerprint=fingerprint, parchi_ids=("parchi-999",)))
    assert second.parchi_ids == ("parchi-001",), "claim overwrote or replaced the existing run"


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_complete_stamps_the_run(adapter_name, request):
    """The stamp has to actually land. Asserting only that two calls agree would pass while
    `completed_at` stayed None the whole time."""
    store = request.getfixturevalue(adapter_name)
    fresh = run()
    store.claim(fresh)
    store.complete(fresh.fingerprint, completed_at=NOW)
    completed = store.get(fresh.fingerprint)
    assert completed.completed_at == NOW
    assert completed.status is StandingOrderStatus.COMPLETED


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_complete_is_idempotent(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    fresh = run()
    store.claim(fresh)
    store.complete(fresh.fingerprint, completed_at=NOW)
    first = store.get(fresh.fingerprint).completed_at
    store.complete(fresh.fingerprint, completed_at=NOW.replace(hour=23))
    assert store.get(fresh.fingerprint).completed_at == first, (
        "a second complete moved the completion time; the first one is the record"
    )


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_complete_refuses_an_unknown_fingerprint(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    with pytest.raises(KeyError):
        store.complete(f"fp-{uuid4()}", completed_at=NOW)


@pytest.mark.parametrize("adapter_name", TRIGGER_RUN_ADAPTERS)
def test_get_returns_none_for_unknown(adapter_name, request):
    assert request.getfixturevalue(adapter_name).get("nope") is None


@pytest.fixture
def memory_standing_orders():
    return InMemoryStandingOrderStore()


@pytest.fixture
def dynamo_standing_orders(dynamo_tables):
    from aadesh_adapters.store.dynamo.standing_order import DynamoStandingOrderStore

    return DynamoStandingOrderStore()


STANDING_ORDER_ADAPTERS = [
    "memory_standing_orders",
    pytest.param("dynamo_standing_orders", marks=pytest.mark.integration),
]


@pytest.mark.parametrize("adapter_name", STANDING_ORDER_ADAPTERS)
def test_standing_order_store_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), StandingOrderStore)


@pytest.mark.parametrize("adapter_name", STANDING_ORDER_ADAPTERS)
def test_a_standing_order_round_trips_whole(adapter_name, request):
    """Every field, including `site_id` -- which is the GSI key as well as a dataclass field,
    so an adapter that strips it from the item on read cannot reconstruct the order at all."""
    store = request.getfixturevalue(adapter_name)
    order = standing_order()
    store.save(order)
    restored = store.get(order.standing_order_id)
    assert restored == order


@pytest.mark.parametrize("adapter_name", STANDING_ORDER_ADAPTERS)
def test_for_site_returns_only_that_sites_orders(adapter_name, request):
    store = request.getfixturevalue(adapter_name)
    mine = standing_order(site_id="site-a")
    theirs = standing_order(site_id="site-b")
    store.save(mine)
    store.save(theirs)
    found = store.for_site("site-a")
    assert {o.standing_order_id for o in found} == {mine.standing_order_id}


@pytest.mark.parametrize("adapter_name", STANDING_ORDER_ADAPTERS)
def test_saving_again_under_the_same_id_replaces_the_order(adapter_name, request):
    """A standing order is mutable until it is triggered; `save` is an upsert, not a
    create-only write. The create-only guarantee lives on `TriggerRunStore.claim`."""
    from dataclasses import replace

    store = request.getfixturevalue(adapter_name)
    order = standing_order()
    store.save(order)
    store.save(replace(order, status=StandingOrderStatus.ACTIVE))
    assert store.get(order.standing_order_id).status is StandingOrderStatus.ACTIVE
```

- [ ] **Step 2: Add the `site_id` GSI to the contract fixture**

`for_site` queries an index that `tests/contract/conftest.py` does not create yet. In `_SIMPLE_TABLES`, `standing_orders` is currently a bare key-only table. Give it its own definition alongside `_PARCHI_TABLE`, and leave `_SIMPLE_TABLES` holding only the three tables that genuinely need no index:

```python
_STANDING_ORDER_TABLE = {
    "TableName": TABLES["standing_orders"],
    "KeySchema": [{"AttributeName": "standing_order_id", "KeyType": "HASH"}],
    "AttributeDefinitions": [
        {"AttributeName": "standing_order_id", "AttributeType": "S"},
        {"AttributeName": "site_id", "AttributeType": "S"},
    ],
    "BillingMode": "PAY_PER_REQUEST",
    "GlobalSecondaryIndexes": [
        {
            "IndexName": "site_id-index",
            "KeySchema": [{"AttributeName": "site_id", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        }
    ],
}

_SIMPLE_TABLES = {
    TABLES["operational"]: "pk",
    TABLES["trigger_runs"]: "fingerprint",
    TABLES["sites"]: "site_id",
}
```

and create it with the same guard the others use:

```python
    if TABLES["standing_orders"] not in existing:
        client.create_table(**_STANDING_ORDER_TABLE)
```

Add `TABLES["standing_orders"]` to the waiter loop.

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/contract/test_standing_order_store_contract.py -m integration -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement both stores**

```python
# services/aadesh_adapters/store/dynamo/standing_order.py
"""DynamoDB persistence for Standing Orders and their trigger runs.

`claim` is create-if-absent, but its contract is to RETURN the existing run rather than raise.
So the conditional write is allowed to fail and the adapter reads back the winner: the caller
is a Step Functions retry, and a retry cannot be handed an exception it has no way to resolve.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from aadesh_core.domain.enums import StandingOrderStatus
from aadesh_core.standing_order.models import StandingOrder, TriggerRun

from aadesh_adapters.store.dynamo.client import (
    TABLES,
    ConditionalCheckFailed,
    conditional_write,
    dynamo_resource,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads


class DynamoStandingOrderStore:
    def __init__(self, *, table_name: str | None = None) -> None:
        self._table_name = table_name or TABLES["standing_orders"]
        self._resource = None

    @property
    def _table(self) -> Any:
        if self._resource is None:
            self._resource = dynamo_resource()
        return self._resource.Table(self._table_name)

    def get(self, standing_order_id: str) -> StandingOrder | None:
        item = self._table.get_item(
            Key={"standing_order_id": standing_order_id}
        ).get("Item")
        if not item:
            return None
        # The whole item goes back in, `site_id` included. `dumps` writes every declared field,
        # so `site_id` is both the GSI key and a field `loads` requires; stripping it here would
        # make `loads` refuse the record for a missing field.
        return loads(item, StandingOrder)

    def save(self, order: StandingOrder) -> None:
        self._table.put_item(Item=dumps(order))

    def for_site(self, site_id: str) -> Sequence[StandingOrder]:
        response = self._table.query(
            IndexName="site_id-index",
            KeyConditionExpression="site_id = :s",
            ExpressionAttributeValues={":s": site_id},
        )
        return tuple(loads(i, StandingOrder) for i in response.get("Items", ()))


class DynamoTriggerRunStore:
    def __init__(self, *, table_name: str | None = None) -> None:
        self._table_name = table_name or TABLES["trigger_runs"]
        self._resource = None

    @property
    def _table(self) -> Any:
        if self._resource is None:
            self._resource = dynamo_resource()
        return self._resource.Table(self._table_name)

    def claim(self, run: TriggerRun) -> TriggerRun:
        try:
            with conditional_write():
                # `dumps(run)` already emits `fingerprint` -- it is a field of TriggerRun -- so
                # it is the table key without any extra work.
                self._table.put_item(
                    Item=dumps(run),
                    ConditionExpression="attribute_not_exists(fingerprint)",
                )
            return run
        except ConditionalCheckFailed:
            existing = self.get(run.fingerprint)
            if existing is None:  # pragma: no cover - only on a concurrent delete
                raise
            return existing

    def get(self, fingerprint: str) -> TriggerRun | None:
        item = self._table.get_item(Key={"fingerprint": fingerprint}).get("Item")
        return loads(item, TriggerRun) if item else None

    def complete(self, fingerprint: str, *, completed_at: datetime | None = None) -> None:
        existing = self.get(fingerprint)
        if existing is None:
            raise KeyError(f"No trigger run for fingerprint {fingerprint!r}.")
        if existing.completed_at is not None:
            return
        updated = replace(
            existing,
            status=StandingOrderStatus.COMPLETED,
            completed_at=completed_at or datetime.now(UTC),
        )
        # The condition is on `completed`, a column that ONLY this method writes, NOT on
        # `completed_at`. `dumps` writes every declared field, so an unfinished run is stored
        # with `completed_at` present as a typed NULL -- and DynamoDB counts a typed NULL as
        # present, so `attribute_not_exists(completed_at)` would be false on the very first
        # completion and every run would silently stay open.
        try:
            with conditional_write():
                self._table.put_item(
                    Item={**dumps(updated), "completed": True},
                    ConditionExpression="attribute_not_exists(completed)",
                )
        except ConditionalCheckFailed:
            pass  # Someone completed it first; idempotent by contract.
```

`loads(item, TriggerRun)` takes the whole item including the key, which is a `TriggerRun` field, so it resolves; for `StandingOrder` the key is `standing_order_id`, also a field. Only the `standing_orders` index from Step 2 is needed — `trigger_runs` is read by primary key only.

- [ ] **Step 5: Run both halves**

Run: `uv run pytest tests/contract/test_standing_order_store_contract.py -m "not integration" -v`
Expected: PASS

Run: `uv run pytest tests/contract/test_standing_order_store_contract.py -m integration -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/aadesh_adapters/store/dynamo/standing_order.py \
        tests/contract/test_standing_order_store_contract.py tests/contract/conftest.py
git commit -m "feat(adapters): add DynamoDB standing-order and trigger-run stores"
```

---

### Task 10: `S3Corpus`

Materialises the corpus to `/tmp`, keyed by the S3 `versionId` of `manifest.json`. This is the task that answers Review Focus #4: a stale or half-written tree must never be verified as if it were the corpus in S3.

**Files:**
- Create: `services/aadesh_adapters/corpus/s3.py`
- Test: `tests/unit/test_s3_corpus.py`

**Interfaces:**
- Consumes: `LocalFileCorpus` — `S3Corpus` is a materialiser plus a delegate, not a reimplementation. `snapshot()`, `obligations()`, `invoked_stage()` and the rest all forward to it.
- Produces: `S3Corpus(*, bucket: str, client: Any, prefix: str = "", cache_dir: Path = Path("/tmp/aadesh-corpus"))` with `sync()`, satisfying `RulesCorpus`, `SourceDocumentStore` and `InvokedStageSource`. The client is injected — `s3_client()` (Task 4) supplies it in production, a fake in tests.

- [ ] **Step 1: Write the failing test**

Uses a fake S3 client, so it runs offline and needs no Docker.

```python
# tests/unit/test_s3_corpus.py
"""Materialisation is keyed on the manifest version.

The failure this prevents: a warm container serving yesterday's corpus under today's version
key, so `make verify` re-proves citations against bytes that are no longer the source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aadesh_adapters.corpus.s3 import S3Corpus, _is_complete


class FakeS3:
    """Minimal stand-in: versionId per manifest write, and an object body map."""

    def __init__(self, objects: dict[str, bytes], version: str = "v1") -> None:
        self.objects = objects
        self.version = version
        self.gets: list[str] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        self.gets.append(Key)
        return {
            "Body": _Body(self.objects[Key]),
            "VersionId": self.version if Key.endswith("manifest.json") else "obj-v1",
        }

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict:
        return {
            "Contents": [{"Key": k} for k in self.objects if k.startswith(Prefix)],
            "IsTruncated": False,
        }


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def corpus_objects() -> dict[str, bytes]:
    """The smallest tree `LocalFileCorpus` will accept, mirrored from CorpusBuilder."""
    return {
        "manifest.json": b'{"documents": []}',
    }


def test_first_sync_writes_the_tree(tmp_path: Path) -> None:
    s3 = FakeS3(corpus_objects())
    corpus = S3Corpus(bucket="b", client=s3, cache_dir=tmp_path)
    corpus.sync()
    assert (tmp_path / "manifest.json").exists()


def test_a_second_sync_with_the_same_version_does_not_refetch(tmp_path: Path) -> None:
    s3 = FakeS3(corpus_objects())
    corpus = S3Corpus(bucket="b", client=s3, cache_dir=tmp_path)
    corpus.sync()
    before = list(s3.gets)
    corpus.sync()
    assert s3.gets == before, "a warm container re-downloaded an unchanged corpus"


def test_a_new_version_invalidates_the_cache(tmp_path: Path) -> None:
    s3 = FakeS3(corpus_objects())
    corpus = S3Corpus(bucket="b", client=s3, cache_dir=tmp_path)
    corpus.sync()
    s3.version = "v2"
    before = len(s3.gets)
    corpus.sync()
    assert len(s3.gets) > before, "a corpus version change must re-materialise"


def test_an_unversioned_manifest_is_never_used_as_a_cache_key(tmp_path: Path) -> None:
    s3 = FakeS3(corpus_objects(), version=None)  # type: ignore[arg-type]
    corpus = S3Corpus(bucket="b", client=s3, cache_dir=tmp_path)
    corpus.sync()
    before = len(s3.gets)
    corpus.sync()
    assert len(s3.gets) > before, (
        "with no versionId there is no change token, so every request must re-sync rather "
        "than treat None as a cache key"
    )


def test_a_partially_written_tree_is_not_treated_as_complete(tmp_path: Path) -> None:
    """A crash mid-sync must leave a tree that is obviously incomplete."""
    assert not _is_complete(tmp_path)
    (tmp_path / "manifest.json").write_bytes(b"{}")
    assert _is_complete(tmp_path)


def test_a_failed_sync_removes_its_marker_so_the_next_attempt_retries(tmp_path: Path) -> None:
    s3 = FakeS3({})  # every get raises KeyError
    corpus = S3Corpus(bucket="b", client=s3, cache_dir=tmp_path)
    with pytest.raises(Exception):
        corpus.sync()
    assert not (tmp_path / ".sync-complete").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_s3_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.corpus.s3'`

- [ ] **Step 3: Implement it**

The completeness marker is written **last**, after every object has landed. That is what makes a crash mid-sync safe: the tree is only ever adopted once it is whole.

```python
# services/aadesh_adapters/corpus/s3.py
"""The corpus, materialised from S3 into /tmp and then read exactly as the local one is.

Why materialise instead of bundling the corpus into the image: bundling would make S3
decorative, and `make verify` would hash the image's copy rather than the authoritative bytes.
The point of the corpus is that verification re-reads what you actually have.

Why the versionId: `LocalFileCorpus.snapshot()` re-hashes every source document on every call,
by design. On Lambda that would mean re-reading the CAQM PDFs from S3 per request. Keying the
cache on the manifest's S3 versionId makes a warm container skip the re-sync while still
re-materialising the moment the corpus itself changes. When there is no versionId -- an
unversioned bucket -- None is NOT used as a cache key, because "no change token" is not the
same as "unchanged".
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain.models import (
    Entitlement,
    InvokedStage,
    Obligation,
    SourceDocument,
    StageBand,
    VerifiedCorpus,
)
from aadesh_core.verification import VerificationReport

_MARKER = ".sync-complete"
_VERSION_FILE = ".corpus-version"
_DEFAULT_CACHE = Path("/tmp/aadesh-corpus")


def _is_complete(cache_dir: Path) -> bool:
    return (cache_dir / _MARKER).exists() and (cache_dir / "manifest.json").exists()


class S3Corpus:
    """A materialising delegate over `LocalFileCorpus`.

    Every reading method forwards to a `LocalFileCorpus` rooted at the cache directory, after
    ensuring the cache matches S3. There is no second implementation of the corpus rules, so
    the S3 path and the local path cannot diverge in how they interpret a citation.
    """

    def __init__(
        self,
        *,
        bucket: str,
        client: Any,
        prefix: str = "",
        cache_dir: Path = _DEFAULT_CACHE,
    ) -> None:
        self._bucket = bucket
        self._client = client
        self._prefix = prefix
        self._cache_dir = Path(cache_dir)
        self._local: LocalFileCorpus | None = None

    def _manifest_version(self) -> str | None:
        response = self._client.get_object(Bucket=self._bucket, Key=f"{self._prefix}manifest.json")
        response["Body"].read()
        return response.get("VersionId")

    def _cached_version(self) -> str | None:
        path = self._cache_dir / _VERSION_FILE
        return path.read_text(encoding="utf-8") if path.exists() else None

    def sync(self) -> None:
        version = self._manifest_version()
        if version is not None and _is_complete(self._cache_dir):
            if self._cached_version() == version:
                return

        staging = self._cache_dir.with_name(self._cache_dir.name + ".staging")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)

        listing = self._client.list_objects_v2(Bucket=self._bucket, Prefix=self._prefix)
        for entry in listing.get("Contents", ()):
            key = entry["Key"]
            relative = key[len(self._prefix):]
            if not relative or relative.endswith("/"):
                continue
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
            target.write_bytes(body.read())

        # Written LAST. A crash before this point leaves a staging tree that is never adopted,
        # so a half-synced corpus cannot be mistaken for the real one.
        (staging / _MARKER).write_text("ok", encoding="utf-8")
        if version is not None:
            (staging / _VERSION_FILE).write_text(version, encoding="utf-8")

        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
        staging.rename(self._cache_dir)
        self._local = None

    @property
    def local(self) -> LocalFileCorpus:
        self.sync()
        if self._local is None:
            self._local = LocalFileCorpus(self._cache_dir)
        return self._local

    # -- every reading method forwards; no corpus rules are reimplemented here ----------

    def snapshot(self) -> VerifiedCorpus:
        return self.local.snapshot()

    def obligations(self) -> tuple[Obligation, ...]:
        return self.local.obligations()

    def entitlements(self) -> tuple[Entitlement, ...]:
        return self.local.entitlements()

    def stage_bands(self) -> tuple[StageBand, ...]:
        return self.local.stage_bands()

    def verification_report(self) -> VerificationReport:
        return self.local.verification_report()

    def documents(self) -> tuple[SourceDocument, ...]:
        return self.local.documents()

    def page_text(self, *, doc_id: str, page: int) -> str | None:
        return self.local.page_text(doc_id=doc_id, page=page)

    def invoked_stage(self) -> InvokedStage | None:
        return self.local.invoked_stage()

    def invocation_history(self) -> tuple[InvokedStage, ...]:
        return self.local.invocation_history()
```

The client is **injected, not constructed**. That keeps boto3 out of the corpus adapter entirely: the tests below pass a fake, and `aadesh_lambda/composition.py` (Task 14) passes a real `boto3.client("s3", endpoint_url=endpoint_url())`. A module that both speaks the corpus rules and builds its own AWS client is a module that cannot be tested without AWS.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_s3_corpus.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Add the port-satisfaction assertion**

Append to `tests/unit/test_s3_corpus.py`:

```python
def test_s3_corpus_satisfies_the_corpus_ports(tmp_path: Path) -> None:
    from aadesh_core.ports.corpus import InvokedStageSource, RulesCorpus, SourceDocumentStore

    corpus = S3Corpus(bucket="b", client=FakeS3(corpus_objects()), cache_dir=tmp_path)
    assert isinstance(corpus, RulesCorpus)
    assert isinstance(corpus, SourceDocumentStore)
    assert isinstance(corpus, InvokedStageSource)
```

Run: `uv run pytest tests/unit/test_s3_corpus.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add services/aadesh_adapters/corpus/s3.py tests/unit/test_s3_corpus.py
git commit -m "feat(adapters): add S3Corpus with version-keyed materialisation"
```

---

### Task 11: `OpenAQProvider`

Review Focus #5 lives here. The port says a reading must declare its provenance; `FixtureAqiProvider` always stamps `SYNTHETIC` with the comment "a placeholder cannot promote itself." `OpenAQProvider` may stamp `MEASURED`, so it must refuse anything it cannot attribute to a known parameter and unit rather than store a plausible-looking number.

**Files:**
- Create: `services/aadesh_adapters/aqi/openaq.py`
- Modify: `tests/contract/test_aqi_provider_contract.py` — add the new adapter to `ADAPTERS`
- Test: `tests/unit/test_openaq_provider.py`

**Interfaces:**
- Consumes: `StationReading`, `Provenance` from `aadesh_core.domain`; `AqiProvider`.
- Produces: `OpenAQProvider(*, api_key: str, station_ids: tuple[str, ...], station_locations: dict[str, int] | None = None, fetch_json: Callable[[str], dict[str, Any]] | None = None, base_url: str = "https://api.openaq.org/v3")`. The transport is an injected `fetch_json` callable rather than a client object, so a test substitutes one lambda and no HTTP library is involved.

- [ ] **Step 1: Write the failing test**

A fake client, so no network and no API key are needed.

```python
# tests/unit/test_openaq_provider.py
"""MEASURED is a claim. It is only made for a reading we can attribute."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aadesh_adapters.aqi.openaq import OpenAQProvider
from aadesh_core.domain import Provenance

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def fetch(payload_dict: dict):
    """Stands in for the HTTP call. The adapter takes a `fetch_json` callable rather than a
    client object, so a test substitutes one lambda and no HTTP library is involved."""

    def _fetch(path: str) -> dict:
        return payload_dict

    return _fetch


def payload(*, parameter="pm25", unit="µg/m³", value=412.0) -> dict:
    return {
        "results": [
            {
                "value": value,
                "parameter": {"name": parameter, "units": unit},
                "datetime": {"utc": NOW.isoformat().replace("+00:00", "Z")},
                "coordinates": {"latitude": 28.7, "longitude": 77.1},
            }
        ]
    }


def provider(payload_dict: dict, *, station: str = "rohini") -> OpenAQProvider:
    return OpenAQProvider(
        api_key="test-key",
        station_ids=(station,),
        fetch_json=fetch(payload_dict),
        station_locations={station: 1234},
    )


def test_station_ids_are_what_was_configured() -> None:
    assert provider(payload()).station_ids() == ("rohini",)


def test_unknown_station_returns_none() -> None:
    assert provider(payload()).latest_reading(station_id="somewhere-else") is None


def test_the_reading_carries_the_parameter_it_was_attributed_to() -> None:
    reading = provider(payload()).latest_reading(station_id="rohini")
    assert reading.parameter == "pm25"


def test_a_recognised_reading_is_labelled_measured() -> None:
    reading = provider(payload()).latest_reading(station_id="rohini")
    assert reading is not None
    assert reading.provenance is Provenance.MEASURED


def test_observed_at_is_timezone_aware() -> None:
    reading = provider(payload()).latest_reading(station_id="rohini")
    assert reading.observed_at.tzinfo is not None


def test_an_unknown_parameter_is_refused_rather_than_stored() -> None:
    """A number we cannot attribute is not a measurement of anything we can name."""
    with pytest.raises(ValueError, match="parameter"):
        provider(payload(parameter="no2")).latest_reading(station_id="rohini")


def test_an_unknown_unit_is_refused_rather_than_stored() -> None:
    """'412' means nothing without knowing it is µg/m³. Storing the number anyway would put a
    plausible-looking figure on a parchi under the label MEASURED."""
    with pytest.raises(ValueError, match="unit"):
        provider(payload(unit="ppb")).latest_reading(station_id="rohini")


def test_an_empty_result_set_returns_none() -> None:
    assert provider({"results": []}).latest_reading(station_id="rohini") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_openaq_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.aqi.openaq'`

- [ ] **Step 3: Implement it**

Read `StationReading`'s exact field list from `services/aadesh_core/domain/models.py` before writing; it already has `is_stale(now, max_age)` and the contract suite asserts `observed_at.tzinfo is not None`.

```python
# services/aadesh_adapters/aqi/openaq.py
"""Live station readings from OpenAQ v3.

This is the only adapter permitted to stamp `Provenance.MEASURED`, so it is the only one that
can put a number on a parchi described as a measurement. That makes refusal its most important
behaviour: a reading whose parameter or unit is not recognised is not a measurement of anything
we can name, and storing it anyway would be worse than storing nothing, because the whole point
of the provenance enum is that MEASURED means measured.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

from aadesh_core.domain import Provenance, StationReading

#: Pollutant -> the only unit we will accept for it. An unrecognised pair is refused.
_ACCEPTED_UNITS: dict[str, str] = {
    "pm25": "µg/m³",
    "pm10": "µg/m³",
}


class OpenAQProvider:
    def __init__(
        self,
        *,
        api_key: str,
        station_ids: tuple[str, ...],
        station_locations: dict[str, int] | None = None,
        fetch_json: Callable[[str], dict[str, Any]] | None = None,
        base_url: str = "https://api.openaq.org/v3",
    ) -> None:
        self._api_key = api_key
        self._station_ids = tuple(station_ids)
        self._locations = dict(station_locations or {})
        self._fetch_json = fetch_json or self._http_get_json
        self._base_url = base_url.rstrip("/")

    def _http_get_json(self, path: str) -> dict[str, Any]:
        """One GET. `urllib.request` rather than a new HTTP dependency: this is a single JSON
        GET, and the default path stays dependency-light.

        The API key travels in a header, never in the URL, so it cannot end up in a log line
        that records the request target.
        """
        # `base_url` defaults to the fixed HTTPS OpenAQ endpoint and only a test overrides it,
        # so the scheme is never attacker-chosen here.
        request = Request(
            f"{self._base_url}{path}",
            headers={"X-API-Key": self._api_key, "Accept": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError(
                f"OpenAQ returned a {type(decoded).__name__} for {path}, expected an object."
            )
        return decoded

    def station_ids(self) -> tuple[str, ...]:
        return self._station_ids

    def latest_reading(self, *, station_id: str) -> StationReading | None:
        if station_id not in self._station_ids:
            return None
        location_id = self._locations.get(station_id)
        if location_id is None:
            return None

        results = self._fetch_json(f"/locations/{location_id}/latest").get("results") or []
        if not results:
            return None

        latest = results[0]
        parameter = str((latest.get("parameter") or {}).get("name", "")).lower()
        unit = str((latest.get("parameter") or {}).get("units", ""))

        if parameter not in _ACCEPTED_UNITS:
            raise ValueError(
                f"OpenAQ returned parameter {parameter!r} for station {station_id!r}, which "
                f"this adapter cannot attribute. Refusing rather than storing a number under "
                f"the label MEASURED."
            )
        if unit != _ACCEPTED_UNITS[parameter]:
            raise ValueError(
                f"OpenAQ returned unit {unit!r} for parameter {parameter!r}. Without a known "
                f"unit the number is not a measurement of anything nameable."
            )

        observed_at = _parse_utc(latest)
        # `StationReading` has no `unit` field: the accepted unit is fixed per parameter by
        # `_ACCEPTED_UNITS` above, and `parameter` is what the record is attributed to.
        return StationReading(
            station_id=station_id,
            parameter=parameter,
            value=float(latest["value"]),
            observed_at=observed_at,
            ingested_at=datetime.now(observed_at.tzinfo),
            provenance=Provenance.MEASURED,
        )


def _parse_utc(latest: dict[str, Any]) -> datetime:
    raw = (latest.get("datetime") or {}).get("utc")
    if not isinstance(raw, str):
        raise ValueError(f"OpenAQ result for {latest!r} carries no UTC timestamp.")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"OpenAQ returned a naive timestamp {raw!r}.")
    return parsed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_openaq_provider.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Hold the new adapter to the shared port contract**

In `tests/contract/test_aqi_provider_contract.py`, add a fixture and append to `ADAPTERS`:

```python
@pytest.fixture
def openaq_provider():
    from aadesh_adapters.aqi.openaq import OpenAQProvider
    from tests.support.openaq_fake import OPENAQ_STATION, openaq_fetch

    return OpenAQProvider(
        api_key="test-key",
        station_ids=(OPENAQ_STATION,),
        station_locations={OPENAQ_STATION: 1234},
        fetch_json=openaq_fetch(),
    )


ADAPTERS = ["fixture_provider", "openaq_provider"]
```

Create `tests/support/openaq_fake.py`. It holds a canned response and a `fetch_json` stand-in, so the OpenAQ adapter can be held to the same contract as the fixture adapter **on the default offline path** — no `integration` marker, no network, no API key.

```python
# tests/support/openaq_fake.py
"""A canned OpenAQ response, so the OpenAQ adapter can join the shared contract suite."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

OPENAQ_STATION = "rohini"

#: Fixed, so the contract suite's assertions are stable across runs.
OPENAQ_OBSERVED_AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def openaq_payload(
    *, parameter: str = "pm25", unit: str = "µg/m³", value: float = 412.0
) -> dict[str, Any]:
    return {
        "results": [
            {
                "value": value,
                "parameter": {"name": parameter, "units": unit},
                "datetime": {"utc": OPENAQ_OBSERVED_AT.isoformat().replace("+00:00", "Z")},
                "coordinates": {"latitude": 28.7, "longitude": 77.1},
            }
        ]
    }


def openaq_fetch(payload: dict[str, Any] | None = None) -> Callable[[str], dict[str, Any]]:
    canned = payload if payload is not None else openaq_payload()

    def _fetch(path: str) -> dict[str, Any]:
        return canned

    return _fetch
```

Run: `uv run pytest tests/contract/test_aqi_provider_contract.py -v`
Expected: PASS. `test_a_returned_reading_always_declares_its_provenance` and `test_observed_at_is_timezone_aware` now run against both adapters, and `test_unknown_station_returns_none_rather_than_raising` now covers the OpenAQ path too.

- [ ] **Step 6: Commit**

```bash
git add services/aadesh_adapters/aqi/openaq.py tests/unit/test_openaq_provider.py \
        tests/support/openaq_fake.py tests/contract/test_aqi_provider_contract.py
git commit -m "feat(adapters): add OpenAQProvider, which refuses a reading it cannot attribute"
```

---

### Task 12: `CloudWatchAuditLog`

`AuditLog.record` "MUST NOT raise — losing an audit line must not fail a halt." `StdoutAuditLog` already has that shape, printing JSON and reporting a sink failure to stderr. The AWS version adds one thing: an EMF block so a denial becomes a CloudWatch metric without a separate agent.

**Files:**
- Create: `services/aadesh_adapters/audit/cloudwatch.py`
- Test: `tests/unit/test_cloudwatch_audit.py`

**Interfaces:**
- Consumes: `AuditLog`.
- Produces: `CloudWatchAuditLog(*, stream: TextIO | None = None)`, emitting one JSON line per event; for events in `DENIAL_EVENTS` it also emits an EMF `_aws` block with `AuthorizationDenials`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cloudwatch_audit.py
"""The audit sink must never raise, and a denial must be countable."""

from __future__ import annotations

import io
import json

from aadesh_adapters.audit.cloudwatch import DENIAL_EVENTS, CloudWatchAuditLog
from aadesh_core.ports.audit import AuditLog


def test_satisfies_the_port() -> None:
    assert isinstance(CloudWatchAuditLog(stream=io.StringIO()), AuditLog)


def test_writes_one_json_line_per_event() -> None:
    stream = io.StringIO()
    CloudWatchAuditLog(stream=stream).record(event="parchi.sealed", detail={"parchi_id": "p1"})
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 1
    assert lines[0]["event"] == "parchi.sealed"
    assert lines[0]["detail"] == {"parchi_id": "p1"}


def test_a_denial_emits_an_emf_block() -> None:
    """Embedded Metric Format: CloudWatch reads the metric straight off the log line, so no
    separate put_metric_data call and no IAM permission for one."""
    stream = io.StringIO()
    CloudWatchAuditLog(stream=stream).record(
        event=sorted(DENIAL_EVENTS)[0], detail={"policy_id": "no-proxy-acknowledgement"}
    )
    emitted = json.loads(stream.getvalue().splitlines()[0])
    assert "_aws" in emitted
    assert emitted["AuthorizationDenials"] == 1


def test_the_declared_emf_dimension_is_actually_emitted() -> None:
    """EMF resolves each declared dimension by reading a member of that name from the root of
    the object. Declaring a dimension the payload never emits publishes the metric against the
    literal value `undefined` -- the alarm would then watch a series nothing writes to."""
    stream = io.StringIO()
    CloudWatchAuditLog(stream=stream).record(event=sorted(DENIAL_EVENTS)[0], detail={})
    emitted = json.loads(stream.getvalue().splitlines()[0])
    declared = emitted["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
    for dimension_group in declared:
        for name in dimension_group:
            assert name in emitted, f"dimension {name!r} is declared but not emitted"
            assert emitted[name] != "undefined"


def test_a_non_denial_event_has_no_emf_block() -> None:
    stream = io.StringIO()
    CloudWatchAuditLog(stream=stream).record(event="parchi.opened", detail={})
    assert "_aws" not in json.loads(stream.getvalue().splitlines()[0])


def test_an_unserialisable_detail_does_not_raise() -> None:
    """The port says MUST NOT raise. A halt must not fail because an audit payload was odd."""
    stream = io.StringIO()
    CloudWatchAuditLog(stream=stream).record(event="odd", detail={"when": object()})
    assert stream.getvalue().strip(), "the event disappeared entirely"


def test_a_broken_stream_does_not_raise() -> None:
    class Broken(io.StringIO):
        def write(self, _: str) -> int:
            raise OSError("pipe closed")

    CloudWatchAuditLog(stream=Broken()).record(event="x", detail={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cloudwatch_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_adapters.audit.cloudwatch'`

- [ ] **Step 3: Implement it**

```python
# services/aadesh_adapters/audit/cloudwatch.py
"""Audit sink for AWS: one JSON line per event on stdout, which CloudWatch Logs collects.

Denials additionally carry an Embedded Metric Format block, so `AuthorizationDenials` becomes a
real metric without a second API call and without granting this function `cloudwatch:
PutMetricData`. Lambda writes to its own log group; the metric filter and alarm live in CDK.

Modelled on `StdoutAuditLog`, including its most important property: `record` does not raise.
The port is explicit that losing an audit line must not fail a halt.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

#: Events that count as an authorization denial. Matched on the event name the authorization
#: service already emits, so the metric needs no change to the core.
DENIAL_EVENTS = frozenset({"authorization.denied"})

_METRIC_NAMESPACE = "Aadesh"
_EMF_DIMENSION = "Service"
_EMF_SERVICE = "aadesh"


class CloudWatchAuditLog:
    def __init__(self, *, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def record(self, *, event: str, detail: Mapping[str, Any]) -> None:
        try:
            now = datetime.now(UTC)
            payload: dict[str, Any] = {
                "ts": now.isoformat(),
                "event": event,
                "detail": dict(detail),
            }
            if event in DENIAL_EVENTS:
                payload["AuthorizationDenials"] = 1
                # EMF resolves a declared dimension by reading the member of that name from the
                # ROOT of the object. Declaring "Service" without emitting `Service` publishes
                # the metric with the literal dimension value `undefined`, so the alarm would
                # sit on one series while the code emitted another.
                payload[_EMF_DIMENSION] = _EMF_SERVICE
                payload["_aws"] = {
                    "Timestamp": int(now.timestamp() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": _METRIC_NAMESPACE,
                            "Dimensions": [[_EMF_DIMENSION]],
                            "Metrics": [
                                {"Name": "AuthorizationDenials", "Unit": "Count"}
                            ],
                        }
                    ],
                }
            # `default=str` rather than a stricter encoder: an audit payload is diagnostic, and
            # a value the encoder cannot name must not cost the whole line.
            self._stream.write(json.dumps(payload, default=str, sort_keys=True) + "\n")
        except Exception as exc:
            # A bare `except Exception` with no noqa, exactly as `StdoutAuditLog` has: the port
            # says `record` MUST NOT raise, because losing an audit line must not abort a halt
            # that is legally in force.
            try:
                print(f"AUDIT SINK FAILED for {event!r}: {exc}", file=sys.stderr)
            except Exception:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cloudwatch_audit.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add services/aadesh_adapters/audit/cloudwatch.py tests/unit/test_cloudwatch_audit.py
git commit -m "feat(adapters): add CloudWatchAuditLog with an EMF denial metric"
```

---

### Task 13: Extract `AadeshApplication` and make the route table declarative

`Demo` builds its own stores inside `__init__`, so it cannot run against DynamoDB, and its routes are two `if/elif` chains that a second skin would have to duplicate. This task makes both shareable and **deletes `_payloads`**, which the spec correction established cannot be replaced by a lookup.

**Files:**
- Create: `services/aadesh_app/__init__.py`, `services/aadesh_app/application.py`, `services/aadesh_app/routes.py`
- Modify: `services/aadesh_web/server.py`, `pyproject.toml`
- Test: `tests/unit/test_application_routes.py`

**Interfaces:**
- Consumes: every port from Tasks 1–12.
- Produces: `ApplicationPorts`, a frozen dataclass of the ten injected ports (`corpus`, `documents`, `invocations`, `parchis`, `tokens`, `ledger`, `task_tokens`, `audit`, `clock`, `authz`); `AadeshApplication(*, ports: ApplicationPorts, site: ConstructionSite, roster: Roster, registered: frozenset[str], corpus_root: Path)`; `ROUTES: tuple[Route, ...]` where `Route(method, path, action, params)`; and `AadeshApplication.dispatch(method: str, path: str, *, query: Mapping[str, str], body: Mapping[str, Any], principal: Principal | None) -> tuple[int, dict[str, Any]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_application_routes.py
"""One route table, read by every skin. Two hand-maintained lists would drift, and the drift
test would be the thing that was supposed to catch it."""

from __future__ import annotations

from aadesh_app.routes import ROUTES, route_for

EXPECTED = {
    ("GET", "/api/health"),
    ("GET", "/api/supervisor"),
    ("GET", "/api/roster"),
    ("GET", "/api/roster/qr"),
    ("GET", "/api/worker"),
    ("GET", "/api/facilitator"),
    ("GET", "/api/verify"),
    ("GET", "/api/impact"),
    ("POST", "/api/standing-order"),
    ("POST", "/api/roster/qr"),
    ("POST", "/api/worker/acknowledge"),
    ("POST", "/api/cedar/supervisor-acknowledge"),
}


def test_the_route_table_covers_every_existing_path() -> None:
    assert {(r.method, r.path) for r in ROUTES} == EXPECTED


def test_route_paths_are_unique() -> None:
    keys = [(r.method, r.path) for r in ROUTES]
    assert len(keys) == len(set(keys))


def test_unknown_route_returns_none_rather_than_raising() -> None:
    assert route_for("GET", "/api/nope") is None


def test_acknowledge_declares_no_identity_parameter() -> None:
    """The route must not accept a worker id from the client. Identity comes from the
    authenticated principal, or the acknowledgement boundary is theatre."""
    route = route_for("POST", "/api/worker/acknowledge")
    assert route is not None
    assert "worker_id" not in route.params, (
        "/api/worker/acknowledge must not read a worker id from the request body: any client "
        "could then acknowledge any worker's parchi by naming them."
    )


def test_facilitator_and_cedar_routes_also_take_no_identity() -> None:
    for method, path in [
        ("GET", "/api/facilitator"),
        ("POST", "/api/cedar/supervisor-acknowledge"),
    ]:
        route = route_for(method, path)
        assert "facilitator_id" not in route.params
        assert "principal_id" not in route.params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_application_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_app'`

- [ ] **Step 3: Write the route table**

Capture the twelve paths from `server.py`'s `_route_get`/`_route_post` exactly as they are today. `params` names only non-identity inputs.

```python
# services/aadesh_app/routes.py
"""The one route table.

Both the local `http.server` skin and the API Gateway skin read this. Keeping one table is what
makes a parity test meaningful: two hand-maintained lists can be compared only by a test that
would itself drift.

Note what is NOT here: no route declares a `worker_id`, `facilitator_id` or `principal_id`
parameter. Identity is derived from verified claims in the skin and passed in as a `Principal`.
`server.py` used to take `worker_id` from the request body, which meant any client could
acknowledge any worker's parchi by naming them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Route:
    method: str
    path: str
    action: str
    #: Non-identity inputs read from the query string or body. Order is significant for
    #: positional extraction.
    params: tuple[str, ...] = ()


ROUTES: tuple[Route, ...] = (
    Route("GET", "/api/health", "health"),
    Route("GET", "/api/supervisor", "supervisor", ("scenario", "reading")),
    Route("GET", "/api/roster", "impact"),
    Route("GET", "/api/roster/qr", "roster_qr", ("scenario",)),
    Route("GET", "/api/worker", "worker_view", ("payload",)),
    Route("GET", "/api/facilitator", "facilitator"),
    Route("GET", "/api/verify", "verify"),
    Route("GET", "/api/impact", "public_impact"),
    Route("POST", "/api/standing-order", "create_standing_order", ("scenario",)),
    Route("POST", "/api/roster/qr", "roster_qr", ("scenario",)),
    Route("POST", "/api/worker/acknowledge", "acknowledge", ("payload",)),
    Route("POST", "/api/cedar/supervisor-acknowledge", "cedar_supervisor_acknowledge"),
)

_BY_KEY = {(r.method, r.path): r for r in ROUTES}


def route_for(method: str, path: str) -> Route | None:
    return _BY_KEY.get((method.upper(), path))
```

- [ ] **Step 4: Run the route-table tests**

Run: `uv run pytest tests/unit/test_application_routes.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write `AadeshApplication`**

Move `Demo`'s twelve methods here unchanged, with these three differences only:

1. Ports arrive through `ApplicationPorts` instead of being constructed in `__init__`.
2. `_payloads` is **deleted**. `roster_qr` and `cedar_supervisor_acknowledge` obtain a payload by calling `issue_acknowledgement_qr(parchi=..., now=..., tokens=self._ports.tokens)` for a `PENDING_ACK` parchi, per the spec correction.
3. `acknowledge`, `facilitator` and `cedar_supervisor_acknowledge` take a `Principal` argument instead of a client-supplied id.

```python
# services/aadesh_app/application.py
"""The application: the port-injected logic the local server and the Lambda handler share.

Nothing here reads the clock, opens a socket, or imports boto3. Every side effect crosses a
port, which is why the same object runs in `make api` and in Lambda.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aadesh_core.authorization.service import AuthorizationService
from aadesh_core.domain import ConstructionSite, Principal
from aadesh_core.errors import AadeshError
from aadesh_core.parchi_ack.roster import Roster
from aadesh_core.ports.audit import AuditLog
from aadesh_core.ports.authz import AuthorizationProvider
from aadesh_core.ports.clock import Clock
from aadesh_core.ports.corpus import InvokedStageSource, RulesCorpus, SourceDocumentStore
from aadesh_core.ports.parchi_ack import (
    AcknowledgementTokenStore,
    IdempotencyLedger,
    ParchiAckStore,
)
from aadesh_core.ports.task_token import TaskTokenStore
from aadesh_app.routes import route_for

_IDENTITY_ACTIONS = frozenset(
    {"acknowledge", "facilitator", "cedar_supervisor_acknowledge"}
)
"""The only routes whose handler needs to know *who* is asking. Everything else is
authorized inside the handler against the site it already knows."""


@dataclass(frozen=True, slots=True)
class ApplicationPorts:
    """Everything the application needs from the outside world, in one object."""

    corpus: RulesCorpus
    documents: SourceDocumentStore
    invocations: InvokedStageSource
    parchis: ParchiAckStore
    tokens: AcknowledgementTokenStore
    ledger: IdempotencyLedger
    task_tokens: TaskTokenStore
    audit: AuditLog
    clock: Clock
    authz: AuthorizationProvider


class AadeshApplication:
    def __init__(
        self,
        *,
        ports: ApplicationPorts,
        site: ConstructionSite,
        roster: Roster,
        registered: frozenset[str],
        corpus_root: Path,
    ) -> None:
        self._ports = ports
        self._site = site
        self._roster = roster
        self._registered = registered
        self._corpus_root = Path(corpus_root)
        self._authz_service = AuthorizationService(authz=ports.authz)

    # ... `resolve`, `supervisor`, `impact`, `public_impact`, `_worker_standings`,
    # `create_standing_order`, `_provenance`, `_open_parchis`, `roster_qr`, `worker_view`,
    # `acknowledge`, `cedar_supervisor_acknowledge`, `facilitator`, `verify`, `health`
    # move here from `Demo` with the three changes listed above.

    def dispatch(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str],
        body: Mapping[str, Any],
        principal: Principal | None,
    ) -> tuple[int, dict[str, Any]]:
        route = route_for(method, path)
        if route is None:
            return 404, {"error": "NOT_FOUND", "path": path}
        source = query if method.upper() == "GET" else body
        kwargs = {name: str(source.get(name, "")) for name in route.params if name != "scenario"}
        if "scenario" in route.params:
            kwargs["scenario"] = str(source.get("scenario", "replay"))
        if route.action in _IDENTITY_ACTIONS:
            kwargs["principal"] = principal
        try:
            handler = getattr(self, route.action)
            return 200, handler(**kwargs)
        except (AadeshError, ValueError, KeyError) as exc:
            return 400, {"error": type(exc).__name__, "reason": str(exc)}
```

`create_standing_order` and `facilitator` currently assert identity via the module-level `_principal(role)` helper. Replace that helper's call sites with the `principal` argument. **Delete `_principal` from `server.py`** once nothing calls it, or the two-sources-of-identity problem survives the refactor.

- [ ] **Step 6: Rewire `server.py` as a thin skin**

`Handler` keeps `_read_body` and `_send` unchanged. `_route_get` and `_route_post` collapse into one dispatch:

```python
    def _route(self, method: str, query: dict[str, str], body: dict[str, Any]) -> None:
        parsed = urlparse(self.path)
        try:
            status, payload = self.app.dispatch(
                method,
                parsed.path,
                query=query,
                body=body,
                # No authentication on the local skin, by design: it is a demo. The role comes
                # from an explicit switch and is labelled as such in the UI. The Lambda skin
                # derives the principal from verified JWT claims instead.
                principal=self._local_principal(query, body),
            )
        except (AadeshError, ValueError, KeyError) as exc:
            self._send(400, {"error": type(exc).__name__, "reason": str(exc)})
            return
        self._send(status, payload)
```

`serve()` builds an `AadeshApplication` from memory adapters and `local_file`, and binds it the same way it binds `demo` today. Keep `make api` on port 8787 with identical responses — that is the whole point of the refactor.

Add these imports to `server.py` for the new skin:

```python
from aadesh_app.application import AadeshApplication, ApplicationPorts
# Re-exported deliberately, not used here: Task 14's parity test asserts
# `server.ROUTES is aadesh_app.routes.ROUTES`, which is the check that the local skin reads
# the shared table instead of keeping a second copy. The redundant alias is what tells ruff
# this import is an export rather than an unused name.
from aadesh_app.routes import ROUTES as ROUTES
from aadesh_lambda.claims import principal_from_claims
```

`principal_from_claims` is written in Task 14. If you are executing this task before Task 14 exists, leave that import out and have `_local_principal` build the `Principal` from the request's role switch directly — then add the import in Task 14. Do **not** stub `principal_from_claims` here.

In `pyproject.toml`, add `"services/aadesh_app"` to `[tool.hatch.build.targets.wheel].packages`.

- [ ] **Step 7: Run the offline suite**

Run: `make test`
Expected: PASS. Any existing test that called `Demo.acknowledge(payload, worker_id)` positionally will need updating to the new signature — update the call, do **not** restore the `worker_id` parameter.

- [ ] **Step 8: Verify the local API still answers identically**

Run `make api` in one shell and, in another:

```bash
curl -s http://127.0.0.1:8787/api/health
curl -s http://127.0.0.1:8787/api/supervisor | head -c 200
curl -s -X POST http://127.0.0.1:8787/api/roster/qr -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Expected: the same shapes as before the refactor. `roster_qr` now returns freshly minted payloads on each call, which is the corrected behaviour.

- [ ] **Step 9: Commit**

```bash
git add services/aadesh_app services/aadesh_web/server.py pyproject.toml \
        tests/unit/test_application_routes.py
git commit -m "refactor(app): extract AadeshApplication with a declarative route table

Demo constructed its own stores, so it could never run against DynamoDB, and its
routes were two if/elif chains a second skin would have had to duplicate.

Deletes _payloads. The raw QR token is stored nowhere by design, so the dict
cannot be replaced by a lookup; roster_qr now mints on demand through
issue_acknowledgement_qr, and cedar_supervisor_acknowledge does the same.

Identity no longer comes from the request body: acknowledge, facilitator and
cedar_supervisor_acknowledge take a Principal, which the Lambda skin derives
from verified claims.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 14: The Lambda skin and the skin-parity test

The API Gateway handler is thin by construction: it derives a `Principal` from verified claims and calls `dispatch`. The parity test is what stops the two skins drifting.

**Files:**
- Create: `services/aadesh_lambda/__init__.py`, `services/aadesh_lambda/handlers/__init__.py`, `services/aadesh_lambda/handlers/api.py`
- Create: `services/aadesh_lambda/claims.py`
- Create: `services/aadesh_lambda/composition.py`
- Modify: `pyproject.toml`
- Test: `tests/verification/test_skin_parity.py`

**Interfaces:**
- Consumes: `ROUTES`, `AadeshApplication.dispatch`.
- Produces: `principal_from_claims(claims: Mapping[str, Any]) -> Principal`; `handler(event, context)` returning an API Gateway HTTP API v2 response.

- [ ] **Step 1: Write the failing test**

```python
# tests/verification/test_skin_parity.py
"""The two skins must expose the same routes, and identity must come from claims."""

from __future__ import annotations

import pytest

from aadesh_app.routes import ROUTES
from aadesh_lambda.claims import principal_from_claims


def test_local_skin_routes_come_from_the_shared_table() -> None:
    from aadesh_web import server

    assert server.ROUTES is ROUTES, (
        "the local skin must read the shared route table, not keep its own"
    )


def test_principal_id_comes_from_the_custom_claim_not_the_subject() -> None:
    """Cedar compares `resource.worker == principal` as ENTITY equality, and a parchi's worker
    is `worker-001`. A Cognito `sub` UUID can never equal it."""
    principal = principal_from_claims(
        {
            "sub": "8f2a-uuid",
            "cognito:groups": ["worker"],
            "custom:principal_id": "worker-001",
            "custom:assigned_site": "example-piling-site",
        }
    )
    assert principal.principal_id == "worker-001"
    assert principal.principal_id != "8f2a-uuid"
    assert principal.role == "worker"
    assert principal.assigned_site == "example-piling-site"


def test_a_supervisor_carries_an_assigned_site() -> None:
    principal = principal_from_claims(
        {
            "sub": "x",
            "cognito:groups": ["supervisor"],
            "custom:principal_id": "supervisor-001",
            "custom:assigned_site": "example-piling-site",
        }
    )
    assert principal.assigned_site == "example-piling-site"


@pytest.mark.parametrize(
    "claims",
    [
        {},  # no groups
        {"cognito:groups": []},
        {"cognito:groups": ["worker"]},  # no principal_id
        {"cognito:groups": ["admin"], "custom:principal_id": "x"},  # unknown role
    ],
)
def test_unusable_claims_are_refused(claims) -> None:
    with pytest.raises(ValueError):
        principal_from_claims(claims)


def test_a_worker_cannot_name_itself_in_the_request_body() -> None:
    """The route table declares no worker_id parameter, so a body-supplied one is not read."""
    route = next(r for r in ROUTES if r.path == "/api/worker/acknowledge")
    assert "worker_id" not in route.params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/verification/test_skin_parity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aadesh_lambda'`

- [ ] **Step 3: Write the claims mapper**

```python
# services/aadesh_lambda/claims.py
"""Verified Cognito claims -> the Principal Cedar decides on.

Three constraints, each of which the policies make non-negotiable:

  * `principal_id` MUST be `custom:principal_id`, never `sub`. `parchi_resource` builds
    `EntityRef("Principal", parchi.worker_id)` and the policy is `resource.worker == principal`
    -- entity equality on the id. A UUID subject can never equal `worker-001`.
  * `role` MUST be one of the three group names the policies compare against.
  * `assigned_site` MUST come from `custom:assigned_site`, because the supervisor permit
    requires `resource.siteId == principal.assignedSite`.

Custom attributes are user-writable by default on a Cognito app client, so the client must be
created with `writeAttributes` excluding both custom attributes. Otherwise a worker could set
`custom:principal_id` to another worker's id and acknowledge their parchi. That is enforced in
CDK; this module simply refuses to invent a principal it was not given.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aadesh_core.domain import Principal

_ROLES = frozenset({"supervisor", "worker", "facilitator"})


def principal_from_claims(claims: Mapping[str, Any]) -> Principal:
    if not claims:
        raise ValueError("No verified claims were supplied.")

    groups = claims.get("cognito:groups") or []
    roles = [g for g in groups if g in _ROLES]
    if not roles:
        raise ValueError(
            f"Token carries no Aadesh role. Expected one of {sorted(_ROLES)} in "
            f"cognito:groups, got {groups!r}."
        )

    principal_id = str(claims.get("custom:principal_id") or "").strip()
    if not principal_id:
        raise ValueError(
            "Token carries no custom:principal_id. The subject is not usable here: Cedar "
            "compares the parchi's worker to the principal as entities, so the id must be the "
            "same string the roster uses (for example worker-001)."
        )

    assigned_site = claims.get("custom:assigned_site") or None
    return Principal(
        principal_id=principal_id,
        role=roles[0],
        assigned_site=str(assigned_site) if assigned_site else None,
    )
```

- [ ] **Step 4: Write the handler**

```python
# services/aadesh_lambda/handlers/api.py
"""API Gateway HTTP API v2 skin over AadeshApplication.

Deliberately thin. It does three things and delegates everything else: derive the principal
from the authorizer's verified claims, pick the query or body source, and translate the
application's (status, payload) into an HTTP response.
"""

from __future__ import annotations

import json
from typing import Any

from aadesh_core.domain import Principal

from aadesh_lambda.claims import principal_from_claims


def _principal(event: dict[str, Any]) -> Principal | None:
    claims = (event.get("requestContext", {}).get("authorizer", {}) or {}).get("jwt", {})
    raw = claims.get("claims")
    if not raw:
        return None
    return principal_from_claims(raw)


def _response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(payload, ensure_ascii=False, default=str),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    from aadesh_lambda.composition import application

    request = event.get("requestContext", {}).get("http", {})
    method = str(request.get("method", "GET")).upper()
    path = str(request.get("path", "/"))

    try:
        principal = _principal(event)
    except ValueError as exc:
        return _response(401, {"error": "UNAUTHENTICATED", "reason": str(exc)})

    if principal is None:
        return _response(401, {"error": "UNAUTHENTICATED", "reason": "No verified token."})

    query = {k: v for k, v in (event.get("queryStringParameters") or {}).items()}
    body: dict[str, Any] = {}
    if event.get("body"):
        try:
            parsed = json.loads(event["body"])
            body = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return _response(400, {"error": "MALFORMED_BODY"})

    status, payload = application().dispatch(
        method, path, query=query, body=body, principal=principal
    )
    return _response(status, payload)
```

- [ ] **Step 5: Write the composition root**

This is the only module in the repo that names every real adapter at once. It is written now and first **exercised in phase 2**, when there is a deployed environment to point it at; what phase 1 requires of it is that it imports cleanly with the `aws` extra absent, which is why every adapter import lives inside the function body.

```python
# services/aadesh_lambda/composition.py
"""Assemble the real adapters into one `ApplicationPorts`.

The seam between "pure core" and "AWS" is exactly this file. `aadesh_core` and `aadesh_app`
never import anything from here, and nothing here decides anything: it picks a concrete
adapter for each port and hands them over.

Every import is inside `build_application` on purpose. `tests/verification/test_skin_parity.py`
imports `aadesh_lambda.handlers.api`, which imports this module; a module-level `import boto3`
would make the offline suite fail on a machine that has no `aws` extra installed.

`site.json` and `roster.json` are contract objects at the corpus root. Phase 2's corpus sync
must place both in the bucket alongside `manifest.json`, because a Lambda has no fixtures
directory to fall back to -- and inventing a site profile in code is precisely the thing this
system refuses to do.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from aadesh_app.application import AadeshApplication, ApplicationPorts
from aadesh_core.domain import ConstructionSite
from aadesh_core.parchi_ack.roster import Roster, RosterEntry

CACHE_DIR = Path("/tmp/aadesh-corpus")
"""Where `S3Corpus` materialises the bucket. Kept in step with that adapter's own default."""

_SITE_FILE = "site.json"
_ROSTER_FILE = "roster.json"

_APPLICATION: AadeshApplication | None = None


def _site_and_roster() -> tuple[ConstructionSite, Roster, frozenset[str]]:
    """The site profile and roster, read from the materialised corpus.

    Both come from `S3Corpus.sync()`'s cache rather than from this module, so a change to the
    site's facts is a corpus change with a hash, not a code change with a deploy.
    """
    site = ConstructionSite.from_dict(
        json.loads((CACHE_DIR / _SITE_FILE).read_text(encoding="utf-8"))
    )
    payload = json.loads((CACHE_DIR / _ROSTER_FILE).read_text(encoding="utf-8"))
    roster = Roster(
        site_id=site.site_id,
        entries=tuple(
            RosterEntry(
                worker_id=entry["worker_id"],
                display_name=entry["display_name"],
                active=entry.get("active", True),
            )
            for entry in payload["workers"]
        ),
    )
    return site, roster, frozenset(payload["registered"])


def build_application() -> AadeshApplication:
    from aadesh_adapters.audit.cloudwatch import CloudWatchAuditLog
    from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
    from aadesh_adapters.clock.system import SystemClock
    from aadesh_adapters.corpus.s3 import S3Corpus
    from aadesh_adapters.store.dynamo.ack import DynamoAcknowledgementTokenStore
    from aadesh_adapters.store.dynamo.client import s3_client
    from aadesh_adapters.store.dynamo.ledger import DynamoIdempotencyLedger
    from aadesh_adapters.store.dynamo.parchi import DynamoParchiStore
    from aadesh_adapters.store.dynamo.task_token import DynamoTaskTokenStore

    # A lambda's /tmp persists across warm invocations, so sync once and reuse. One S3 GET per
    # cold start is the price of never reading a corpus that does not hash to its manifest.
    corpus = S3Corpus(
        bucket=os.environ["AADESH_CORPUS_BUCKET"],
        client=s3_client(),
        prefix=os.environ.get("AADESH_CORPUS_PREFIX", ""),
        cache_dir=CACHE_DIR,
    )
    corpus.sync()

    site, roster, registered = _site_and_roster()
    policies = Path(os.environ.get("AADESH_CEDAR_DIR", "/var/task/cedar"))

    return AadeshApplication(
        ports=ApplicationPorts(
            corpus=corpus,
            documents=corpus,
            invocations=corpus,
            parchis=DynamoParchiStore(),
            tokens=DynamoAcknowledgementTokenStore(),
            ledger=DynamoIdempotencyLedger(),
            task_tokens=DynamoTaskTokenStore(),
            audit=CloudWatchAuditLog(),
            clock=SystemClock(),
            authz=CedarAuthorizationProvider(
                policy_path=policies / "policies.cedar",
                denials_path=policies / "denials.json",
                schema_path=policies / "schema.cedar",
            ),
        ),
        site=site,
        roster=roster,
        registered=registered,
        corpus_root=CACHE_DIR,
    )


def application() -> AadeshApplication:
    """The process-wide instance. Lambda reuses a warm container, and the corpus is immutable
    within a deployment, so building it once per container is both correct and cheap."""
    global _APPLICATION
    if _APPLICATION is None:
        _APPLICATION = build_application()
    return _APPLICATION


__all__ = ["CACHE_DIR", "application", "build_application"]
```

`DynamoStandingOrderStore` and `DynamoTriggerRunStore` are deliberately absent: neither is a
port on `AadeshApplication`. They belong to the standing-order workflow's own Lambda in phase 4.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/verification/test_skin_parity.py -v`
Expected: PASS (4 tests plus the 4 parametrised cases). None of them calls `handler`, so no AWS
credential is needed.

- [ ] **Step 7: Add the package to the wheel**

In `pyproject.toml`, add `"services/aadesh_lambda"` to `[tool.hatch.build.targets.wheel].packages`.

- [ ] **Step 8: Run the whole offline suite**

Run: `make test && make verify`
Expected: PASS. `make verify` must still report 55 citation checks — this phase changes no corpus data.

- [ ] **Step 9: Commit**

```bash
git add services/aadesh_lambda pyproject.toml tests/verification/test_skin_parity.py
git commit -m "feat(lambda): add the API Gateway skin, its composition root, and a skin-parity test"
```

---

### Task 15: Refuse secrets in the tree

The spec's security constraint is explicit: no AWS keys, Bedrock credentials, secrets, API keys or personal data committed. `tests/support/source_scan.py` already exists for exactly this shape of guard, with a meta-test file proving the scanner can fail.

**Files:**
- Modify: `tests/support/source_scan.py`
- Modify: `tests/unit/test_source_scan_guard.py`
- Test: `tests/unit/test_no_committed_secrets.py`

**Interfaces:**
- Extends `scan_source` with a `"secret"` violation kind; no signature changes.

- [ ] **Step 1: Write the failing meta-test**

Append to `tests/unit/test_source_scan_guard.py`, following the existing convention: each rule gets a "flags a breach" test, a clean-source case, and a suppression test.

```python
SECRET_CLEAN = '''
"""No credentials here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    table_name: str
    region: str = "ap-south-1"
'''


def test_flags_an_aws_access_key_id():
    bad = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n'
    violations = scan_source(bad, path="adapters/aws.py")
    assert any(v.kind == "secret" for v in violations)


def test_flags_a_hardcoded_openaq_key():
    bad = 'OPENAQ_API_KEY = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"\n'
    violations = scan_source(bad, path="adapters/openaq.py")
    assert any(v.kind == "secret" for v in violations)


def test_flags_the_qr_signing_secret():
    bad = 'QR_SIGNING_SECRET = "shhh-this-is-the-real-one"\n'
    violations = scan_source(bad, path="web/qr.py")
    assert any(v.kind == "secret" for v in violations)


def test_flags_an_aws_secret_access_key_assignment():
    bad = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
    violations = scan_source(bad, path="adapters/aws.py")
    assert any(v.kind == "secret" for v in violations)


def test_secret_free_source_produces_no_violations():
    assert scan_source(SECRET_CLEAN, path="adapters/config.py") == []


def test_the_secret_suppression_marker_is_honoured():
    suppressed = (
        'EXAMPLE = "AKIAIOSFODNN7EXAMPLE"  # noqa: aadesh-no-secret\n'
    )
    assert scan_source(suppressed, path="docs/example.py") == []


def test_scan_text_finds_a_secret_without_parsing_python():
    """`scan_text` is what lets the check cover JSON, TOML, YAML and TypeScript.

    It must NOT route through `ast.parse`, and the two inputs below are why. Python reads
    `{"aws_secret_access_key": "..."}` as a dict expression containing no assignment at all,
    so the AST path would find nothing and report a false clean. A `.ts` file it rejects
    outright with `SyntaxError`, which would error the check rather than fail it.
    """
    json_object = '{"aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}\n'
    assert any(
        v.kind == "secret" for v in scan_text(json_object, path="web/package.json")
    ), "a quoted JSON key is the shape a key actually takes in package.json"

    typescript = (
        "const config = {\n"
        '  aws_secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",\n'
        "};\n"
    )
    assert any(v.kind == "secret" for v in scan_text(typescript, path="web/config.ts"))


def test_scan_text_honours_the_suppression_marker():
    bad = 'API_KEY="a1b2c3d4e5f6a7b8"  # noqa: aadesh-no-secret\n'
    assert scan_text(bad, path="docs/example.env") == []
```

Add `scan_text` to the module's existing import from `tests.support.source_scan`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_source_scan_guard.py -v`
Expected: FAIL — the eight new tests fail because no `secret` rule exists.

- [ ] **Step 3: Add the rule**

Two changes to `tests/support/source_scan.py`.

**(a)** Next to `SUPPRESSION_MARKER`, add the second marker and make `_suppressed_lines` honour both, so the suppression rule stays one sentence: *a suppression marker on a line means that line is a deliberate example.*

```python
#: An explicit, reviewable opt-out. Grep-able in review.
SUPPRESSION_MARKER = "noqa: aadesh-no-legal-literal"

#: The same opt-out for the credential rules below.
SECRET_SUPPRESSION_MARKER = "noqa: aadesh-no-secret"

#: Either marker suppresses either rule on its line. One rule is easier to hold in your head
#: than a matrix, and the reason is always the same: this line is a deliberate example.
_SUPPRESSION_MARKERS = (SUPPRESSION_MARKER, SECRET_SUPPRESSION_MARKER)


def _suppressed_lines(source: str) -> set[int]:
    return {
        i
        for i, line in enumerate(source.splitlines(), start=1)
        if any(marker in line for marker in _SUPPRESSION_MARKERS)
    }
```

**(b)** Alongside `_MONEY_NAME_RE` and `_CURRENCY_RE`, add the credential patterns, the `_secrets` rule, and a text-only entry point:

```python
#: Credential shapes that must never appear in a source file. Deliberately blunt and biased
#: towards false positives: a comment quoting an example key is worth an explicit suppression,
#: and a committed live key is not recoverable.
_SECRET_PATTERNS = (
    # AWS access key ids have a fixed, distinctive prefix.
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # A long base64-ish or hex-ish literal assigned to a secret-looking name. `re.MULTILINE`
    # is required: the leading `^\s*` anchors to the start of a line, so without it the rule
    # would only ever match a file whose very first line held a credential.
    (
        "secret-assignment",
        re.compile(
            r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*)?"
            r"(?:SECRET|PASSWORD|API_KEY|APIKEY|ACCESS_KEY|PRIVATE_KEY|TOKEN)"
            r"[A-Za-z0-9_]*[\"']?\s*[:=]\s*[\"'][^\"']{16,}[\"']",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    # `["']?` before the separator is not decoration. In JSON the key is quoted, so the bytes
    # are `"aws_secret_access_key": "..."` and a pattern demanding whitespace between the name
    # and the colon would miss the single most likely place a key gets committed.
    (
        "aws-secret-access-key",
        re.compile(
            r"aws_secret_access_key[\"']?\s*[:=]\s*[\"'][^\"']{16,}[\"']", re.IGNORECASE
        ),
    ),
)


def _line_of(source: str, match: re.Match[str]) -> int:
    return source.count("\n", 0, match.start()) + 1


def _secrets(source: str, path: str) -> Iterator[Violation]:
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(source):
            yield Violation(
                kind="secret",
                path=path,
                line=_line_of(source, match),
                detail=(
                    f"possible hardcoded credential ({kind}). Secrets belong in SSM "
                    f"SecureString or the environment, never in the tree. If this is a "
                    f"documentation example, append '{SECRET_SUPPRESSION_MARKER}'."
                ),
            )


def scan_text(source: str, *, path: str = "<string>") -> list[Violation]:
    """The credential rules over arbitrary text, with no syntax tree.

    `scan_source` starts with `ast.parse`, which cannot read JSON, TOML, YAML, Markdown or
    TypeScript -- it raises rather than reporting. This entry point is what lets the
    committed-secrets check cover `pyproject.toml`, `package.json` and `.env.example` as well
    as `.py`. Suppression is applied here rather than inside `_secrets`, so `scan_source` gets
    it through the same filter as every other rule.
    """
    suppressed = _suppressed_lines(source)
    return sorted(
        (v for v in _secrets(source, path) if v.line not in suppressed),
        key=lambda v: (v.line, v.kind),
    )
```

Register `_secrets` in `scan_source`'s `found` list — the existing `suppressed` filter then applies to it with everything else:

```python
    found = [
        *_numeric_literals(tree, path),
        *_money_constants(tree, path),
        *_currency_symbols(source, path),
        *_secrets(source, path),
    ]
```

- [ ] **Step 4: Run the meta-tests**

Run: `uv run pytest tests/unit/test_source_scan_guard.py -v`
Expected: PASS (16 tests — 8 existing plus the 8 added)

- [ ] **Step 5: Assert the real tree is clean**

```python
# tests/unit/test_no_committed_secrets.py
"""INVARIANTS: no credential is committed anywhere in this repository.

The scanner backing this is proven able to fail in tests/unit/test_source_scan_guard.py.
Without that companion file, a scanner that always returned [] would look like a passing
invariant -- the same reasoning as `make verify-tamper`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.support.source_scan import scan_file, scan_text

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Everything a developer could commit. Data files are included on purpose: a key pasted into
#: a fixture or a README is a committed key, and `.env.example` is the single most likely place
#: for a real key to be pasted "just to try it".
_SCANNED_SUFFIXES = frozenset(
    {".py", ".json", ".toml", ".yaml", ".yml", ".md", ".mjs", ".ts", ".tsx", ".sh"}
)
_SCANNED_NAMES = frozenset({".env.example", ".env.sample", ".env.template"})
_SKIP_DIRS = frozenset(
    {".git", ".venv", "node_modules", ".next", "__pycache__", ".localstack", "htmlcov"}
)


def test_no_secret_in_any_tracked_file() -> None:
    """Uses `git ls-files`, so the check covers exactly what a clone would receive.

    Python goes through the AST path and everything else through the text path. Running
    `scan_file` on a JSON or TOML file would not report a violation, it would raise
    `SyntaxError` -- the check would error out instead of failing.
    """
    listing = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    violations = []
    for relative in listing.stdout.splitlines():
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        if path.suffix not in _SCANNED_SUFFIXES and path.name not in _SCANNED_NAMES:
            continue
        if _SKIP_DIRS & set(Path(relative).parts):
            continue
        if path.suffix == ".py":
            violations.extend(scan_file(path, display_path=relative))
        else:
            violations.extend(
                scan_text(path.read_text(encoding="utf-8"), path=relative)
            )

    secrets = [v for v in violations if v.kind == "secret"]
    assert secrets == [], "\n".join(["Committed credentials found:", *map(str, secrets)])


def test_env_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, ".env must be gitignored; it holds real credentials locally"
```

- [ ] **Step 6: Run it and fix what it finds**

Run: `uv run pytest tests/unit/test_no_committed_secrets.py -v`
Expected: FAIL once, on exactly one line. Across every tracked file the three patterns match exactly one place today:

```
tests/unit/test_parchi_privacy.py:295: [secret] token_reference="tok_0123456789abcdef"
```

That is a deliberate fake token in the privacy test that proves the audit log redacts a token reference. Append the suppression marker to that line:

```python
        token_reference="tok_0123456789abcdef",  # noqa: aadesh-no-secret - a fake, by design
```

Then re-run and expect PASS. **Do not** widen the pattern to exclude it, and never add a real key. If a match appears somewhere else, treat it as a finding and read the line before suppressing it.

- [ ] **Step 7: Run the whole suite**

Run: `make test && make verify && make lint`
Expected: PASS, 55 citation checks, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add tests/support/source_scan.py tests/unit/test_source_scan_guard.py \
        tests/unit/test_no_committed_secrets.py
git commit -m "test(security): refuse a committed credential anywhere in the tree"
```

---

## Phase 1 done when

- [ ] `make test` passes offline with no Docker, no AWS account and no network beyond PyPI.
- [ ] `make verify` still reports 55 citation checks and exits 0.
- [ ] `make verify-tamper` still reports `FAILED (expected)`.
- [ ] `make lint` is clean.
- [ ] `make api` serves the same twelve routes with the same response shapes as before the refactor.
- [ ] With LocalStack running, `make test-integration` passes every contract suite against both adapters.
- [ ] No `_payloads`, and no route reads `worker_id`, `facilitator_id` or `principal_id` from a request.
- [ ] No credential appears in any tracked file.

## Deferred to later phases

- `aadesh_lambda/composition.py` is written but only exercised in phase 2, when there is a deployed environment.
- The `expires_at` TTL attribute on `aadesh-operational` is set by the adapter here and enabled on the table in phase 2.
- The `standing_orders` `site_id` GSI is created in the LocalStack fixture here and in CDK in phase 2.
- Auth on the local skin stays a labelled demo affordance. Phase 3 replaces it with Cognito in the Lambda skin only.
