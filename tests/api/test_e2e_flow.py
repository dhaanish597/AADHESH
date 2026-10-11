"""API-level tests for the token, acknowledgement, consent and Cedar flows.

These drive the REAL application instance -- the same `Demo` wiring the local `http.server`
skin serves -- in-process, so they need no running server and no Docker. Every assertion is
about behaviour the browser demonstration depends on:

  * a supervisor can mint a real, opaque, short-lived single-use token for a synthetic worker;
  * the worker (and only that worker) can view and acknowledge their own Parchi;
  * the acknowledgement is a real lifecycle transition with an audit event, is idempotent on a
    repeat, and refuses a different worker, a reused link and an expired link;
  * a supervisor cannot acknowledge on a worker's behalf (Cedar);
  * a facilitator cannot read the full Parchi (Cedar), is denied assistance without a live
    worker-granted consent, and -- when consent IS granted -- receives only a redacted view;
  * revoking the consent denies the next assistance request.

The `demo-seed` payload is included as a negative case: it is a static fixture and must never
resolve to a real Parchi.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "services") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "services"))

from aadesh_core.errors import AuthorizationDenied, TokenRejected  # noqa: E402
from aadesh_core.parchi_ack.service import acknowledge_parchi  # noqa: E402
from aadesh_core.parchi_ack.tokens import (  # noqa: E402
    TOKEN_SCHEME,
    hash_token,
    parse_acknowledgement_payload,
)
from aadesh_web.server import Demo  # noqa: E402

PARCHI_BANNED_TOKENS = (
    "phone",
    "bank",
    "aadhaar",
    "ifsc",
    "pan",
    "address",
    "obligation_ids",
    "readiness_checklist",
    "source_quote",
    "content_hash",
)


@pytest.fixture()
def app() -> Demo:
    """A fresh in-memory application with its Standing Order and Parchis opened."""
    demo = Demo()
    demo.create_standing_order(scenario="replay")
    return demo


def _pending_worker(demo: Demo) -> dict:
    roster = demo.roster_qr(scenario="replay")
    pending = [w for w in roster["workers"] if w["state"] == "pending_ack" and w["payload"]]
    assert pending, "expected at least one worker with a pending Parchi and a real token"
    return pending[0]


# --------------------------------------------------------------------------- token issuance


def test_token_is_minted_for_a_synthetic_worker(app: Demo) -> None:
    worker = _pending_worker(app)
    payload = worker["payload"]

    assert payload.startswith(TOKEN_SCHEME)
    # The token is opaque: no worker id, no parchi id, no PII in the payload itself.
    raw = payload[len(TOKEN_SCHEME) :]
    assert worker["worker_id"] not in raw
    assert worker["parchi_id"] not in raw
    assert len(raw) >= 43, "a full-entropy token should render as 43+ characters"

    # The raw token is not recoverable from the store -- only its hash is kept.
    token = app.tokens.get(hash_token(raw))
    assert token is not None
    assert token.worker_id == worker["worker_id"]
    assert token.parchi_id == worker["parchi_id"]
    assert token.expires_at > token.issued_at


def test_demo_seed_token_never_resolves(app: Demo) -> None:
    for payload in ("demo-seed", "aadesh://ack/short", "aadesh://ack/../x"):
        with pytest.raises(TokenRejected):
            app.worker_view(payload)


# ------------------------------------------------------------------------- acknowledgement


def test_worker_views_then_acknowledges_own_parchi(app: Demo) -> None:
    worker = _pending_worker(app)

    view = app.worker_view(worker["payload"])
    assert view["status"] == "PENDING"
    assert view["state"] == "pending_ack"
    assert view["worker_id"] == worker["worker_id"]
    assert view["citations"], "the pending view must carry its verified citations"

    outcome = app.acknowledge(worker["payload"], worker["worker_id"])
    assert outcome["parchi"]["state"] == "acknowledged"
    assert outcome["parchi"]["acknowledged_by"] == worker["worker_id"]
    assert outcome["event_id"]
    assert outcome["already_confirmed"] is False

    # The stored record really moved, and a re-read reports the current state.
    stored = app.store.get(outcome["parchi"]["parchi_id"])
    assert stored is not None
    assert stored.state.value == "acknowledged"


def test_wrong_worker_is_refused(app: Demo) -> None:
    worker = _pending_worker(app)
    with pytest.raises((AuthorizationDenied, TokenRejected)):
        app.acknowledge(worker["payload"], "worker-002")

    # The refused attempt changed nothing.
    parchi = app.store.get(worker["parchi_id"])
    assert parchi is not None
    assert parchi.state.value == "pending_ack"


def test_reused_token_is_idempotent_and_emits_one_event(app: Demo) -> None:
    worker = _pending_worker(app)
    first = app.acknowledge(worker["payload"], worker["worker_id"])
    ack_events = len(app.audit.for_event("parchi.acknowledged"))

    second = app.acknowledge(worker["payload"], worker["worker_id"])
    assert second["already_confirmed"] is True
    assert second["event_id"] == first["event_id"]
    assert len(app.audit.for_event("parchi.acknowledged")) == ack_events


def test_expired_token_is_refused(app: Demo) -> None:
    worker = _pending_worker(app)
    raw = parse_acknowledgement_payload(worker["payload"])
    token = app.tokens.get(hash_token(raw))
    assert token is not None

    afterwards = token.expires_at + timedelta(minutes=1)
    with pytest.raises(TokenRejected):
        acknowledge_parchi(
            payload=worker["payload"],
            actor_worker_id=worker["worker_id"],
            now=afterwards,
            store=app.store,
            tokens=app.tokens,
            ledger=app.ledger,
            audit=app.audit,
        )


# ----------------------------------------------------------------------- Cedar denials


def test_supervisor_cannot_acknowledge_on_a_workers_behalf(app: Demo) -> None:
    worker = _pending_worker(app)
    result = app.cedar_supervisor_acknowledge(worker["worker_id"])
    assert result["denied"] is True
    assert result["allowed"] is False
    assert result["policy_id"] == "no-proxy-acknowledgement"

    parchi = app.store.get(worker["parchi_id"])
    assert parchi is not None and parchi.state.value == "pending_ack"


def test_facilitator_cannot_read_the_full_parchi(app: Demo) -> None:
    payload = app.facilitator()
    assert payload["read_attempt"]["allowed"] is False
    assert payload["read_attempt"]["policy_id"] == "assist-is-not-disclosure"


# ---------------------------------------------------------------------- consent + redaction


def test_assistance_without_consent_is_denied(app: Demo) -> None:
    worker = _pending_worker(app)
    result = app.assist(worker_id=worker["worker_id"], parchi_id=worker["parchi_id"])
    assert result["allowed"] is False
    assert result["policy_id"] == "assist-requires-live-consent"
    assert "view" not in result


def test_assistance_with_granted_consent_is_redacted(app: Demo) -> None:
    worker = _pending_worker(app)
    app.acknowledge(worker["payload"], worker["worker_id"])
    grant = app.grant_consent(worker["parchi_id"], worker["worker_id"])
    assert grant["consent_granted"] is True
    assert worker["worker_id"] not in grant["context_id"]
    assert worker["parchi_id"] not in grant["context_id"]

    result = app.assist(worker_id=worker["worker_id"], parchi_id=worker["parchi_id"])
    assert result["allowed"] is True
    view = result["view"]

    # Only the permitted fields are present.
    assert set(view) == {
        "context_id",
        "parchi_id",
        "worker_id",
        "site_id",
        "claim_status",
        "consent_status",
        "consent_granted_at",
        "consent_expires_at",
    }

    # And none of the forbidden payload is anywhere in the serialised response.
    text = json.dumps(result).lower()
    for banned in PARCHI_BANNED_TOKENS:
        assert banned not in text, f"facilitator response leaked: {banned}"


def test_revoked_consent_blocks_subsequent_assistance(app: Demo) -> None:
    worker = _pending_worker(app)
    grant = app.grant_consent(worker["parchi_id"], worker["worker_id"])

    allowed = app.assist(worker_id=worker["worker_id"], parchi_id=worker["parchi_id"])
    assert allowed["allowed"] is True

    revoked = app.revoke_consent(grant["context_id"])
    assert revoked["revoked_at"]

    denied = app.assist(worker_id=worker["worker_id"], parchi_id=worker["parchi_id"])
    assert denied["allowed"] is False
    assert denied["policy_id"] == "assist-requires-live-consent"


def test_expired_consent_blocks_assistance(app: Demo) -> None:
    worker = _pending_worker(app)
    grant = app.grant_consent(worker["parchi_id"], worker["worker_id"])
    # Push the stored consent's window into the past so it reads as expired.
    stored = app._consents[grant["context_id"]]
    from dataclasses import replace

    app._consents[grant["context_id"]] = replace(
        stored,
        granted_at=datetime.now(UTC) - timedelta(days=2),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    denied = app.assist(worker_id=worker["worker_id"], parchi_id=worker["parchi_id"])
    assert denied["allowed"] is False


def test_consent_cannot_be_granted_by_a_non_worker(app: Demo) -> None:
    worker = _pending_worker(app)
    with pytest.raises(ValueError):
        # actor is not the worker: only the worker may grant consent for their own claim.
        from aadesh_core.consent import grant_consent as core_grant

        core_grant(
            context_id="c-x",
            parchi_id=worker["parchi_id"],
            worker_id=worker["worker_id"],
            facilitator_id="facilitator-001",
            granted_at=datetime.now(UTC),
            ttl=timedelta(hours=1),
            actor_worker_id="supervisor-001",
        )
