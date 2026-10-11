"""The AWS consent contract: authenticated grant/revoke, and durable enforcement on assist.

These drive the real `api_handler.handle` over an `AadeshApplication` wired to the durable
consent store, in process. No AWS credentials and no network are required: the store is the
in-memory adapter, which satisfies the same `ConsentStore` contract as the DynamoDB one.

What is pinned here:

  * the granting actor comes from the VERIFIED Cognito principal, never the request body, and
    only the worker named on the Parchi may grant consent;
  * a revocation is persisted, and the NEXT assistance request is denied -- across a separately
    constructed application instance, because that is what "durable" has to mean;
  * a stale grant loses to a revocation instead of restoring it;
  * a consent-store failure fails CLOSED: no authorized assistance response is produced.

The route's authorization is intentionally narrow: the worker's own identity rule lives in
`aadesh_core.consent`, and the handler supplies the actor it resolved from the claims. The
assistance path itself still goes through Cedar, and the facilitator boundary is asserted here
too (a facilitator still cannot read the full Parchi).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.store.memory_consent import InMemoryConsentStore
from aadesh_aws import api_handler
from aadesh_core.domain import Principal
from aadesh_core.errors import ConsentStoreConflict
from aadesh_web.server import FACILITATOR_ID, Demo

FACILITATOR = Principal(principal_id=FACILITATOR_ID, role="facilitator")


def _event(path: str, *, claims: dict, body: dict | None = None, method: str = "POST") -> dict:
    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body or {}),
        "requestContext": {"authorizer": {"claims": {"sub": "cognito-sub", **claims}}},
    }


def _worker_claims(worker_id: str) -> dict:
    return {"custom:role": "worker", "custom:principal_id": worker_id}


def _facilitator_claims() -> dict:
    return {"custom:role": "facilitator", "custom:principal_id": FACILITATOR_ID}


def _body(response: dict) -> dict:
    return json.loads(response["body"])


def _app_with_workers(*, consent_store=None, store=None) -> tuple[Demo, list[dict]]:
    app = Demo(consent_store=consent_store, store=store)
    app.create_standing_order(scenario="replay")
    roster = app.roster_qr(scenario="replay")
    pending = [w for w in roster["workers"] if w["state"] == "pending_ack" and w["payload"]]
    assert len(pending) >= 2, "the demo roster must offer at least two workers with parchis"
    return app, pending


# --------------------------------------------------------------------------- grant


def test_grant_persists_consent_and_reads_back_durably(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_worker_claims(worker["worker_id"]),
            body={"parchi_id": worker["parchi_id"], "worker_id": worker["worker_id"]},
        )
    )

    assert response["statusCode"] == 200
    granted = _body(response)
    assert granted["consent_granted"] is True
    assert granted["worker_id"] == worker["worker_id"]

    live = store.find_live(
        worker_id=worker["worker_id"],
        facilitator_id=FACILITATOR_ID,
        parchi_id=worker["parchi_id"],
        now=datetime.now(UTC),
    )
    assert live is not None, "the grant was reported but not persisted"


def test_grant_is_denied_for_a_facilitator(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_facilitator_claims(),
            body={"parchi_id": worker["parchi_id"], "worker_id": worker["worker_id"]},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "AUTHORIZATION_DENIED"
    assert (
        store.find_live(
            worker_id=worker["worker_id"],
            facilitator_id=FACILITATOR_ID,
            parchi_id=worker["parchi_id"],
            now=datetime.now(UTC),
        )
        is None
    )


def test_grant_is_denied_when_the_actor_is_not_the_named_worker(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    # A signed-in worker naming ANOTHER worker's claim. The actor is from the claims; naming a
    # worker does not grant for them.
    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_worker_claims("worker-002"),
            body={"parchi_id": worker["parchi_id"], "worker_id": worker["worker_id"]},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "CONSENT_REFUSED"
    assert (
        store.find_live(
            worker_id=worker["worker_id"],
            facilitator_id=FACILITATOR_ID,
            parchi_id=worker["parchi_id"],
            now=datetime.now(UTC),
        )
        is None
    )


def test_grant_is_denied_for_a_parchi_the_worker_does_not_own(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    first, second = workers[0], workers[1]

    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_worker_claims(first["worker_id"]),
            body={"parchi_id": second["parchi_id"], "worker_id": first["worker_id"]},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "CONSENT_REFUSED"


def test_grant_is_denied_for_a_missing_parchi(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_worker_claims(worker["worker_id"]),
            body={"parchi_id": "parchi-does-not-exist", "worker_id": worker["worker_id"]},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "CONSENT_REFUSED"


def test_grant_is_denied_when_the_worker_names_themselves_facilitator(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_worker_claims(worker["worker_id"]),
            body={
                "parchi_id": worker["parchi_id"],
                "worker_id": worker["worker_id"],
                "facilitator_id": worker["worker_id"],
            },
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "CONSENT_REFUSED"


# --------------------------------------------------------------------------- revoke


def test_revoke_is_denied_for_a_non_worker(monkeypatch):
    store = InMemoryConsentStore()
    app, _ = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)

    response = api_handler.handle(
        _event(
            "/api/consent/revoke",
            claims=_facilitator_claims(),
            body={"context_id": "ctx-anything"},
        )
    )
    assert response["statusCode"] == 403
    assert _body(response)["error"] == "AUTHORIZATION_DENIED"


def test_revoke_is_denied_for_a_different_worker(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]
    grant = app.grant_consent(worker["parchi_id"], worker["worker_id"])

    response = api_handler.handle(
        _event(
            "/api/consent/revoke",
            claims=_worker_claims("worker-002"),
            body={"context_id": grant["context_id"]},
        )
    )

    assert response["statusCode"] == 403
    assert _body(response)["error"] == "CONSENT_REFUSED"
    # The refusal changed nothing: the consent is still live.
    assert (
        app._live_consent(
            parchi_id=worker["parchi_id"],
            worker_id=worker["worker_id"],
            facilitator_id=FACILITATOR_ID,
            now=datetime.now(UTC),
        )
        is not None
    )


def test_revoke_is_persisted_and_denies_the_next_assistance(monkeypatch):
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]
    grant = app.grant_consent(worker["parchi_id"], worker["worker_id"])

    # Before revocation, assistance under this consent is permitted.
    before = api_handler.handle(
        _event(
            "/api/assist",
            claims=_facilitator_claims(),
            body={"worker_id": worker["worker_id"], "parchi_id": worker["parchi_id"]},
        )
    )
    assert _body(before)["allowed"] is True

    revoked = api_handler.handle(
        _event(
            "/api/consent/revoke",
            claims=_worker_claims(worker["worker_id"]),
            body={"context_id": grant["context_id"]},
        )
    )
    assert revoked["statusCode"] == 200
    assert _body(revoked)["revoked_at"]

    after = api_handler.handle(
        _event(
            "/api/assist",
            claims=_facilitator_claims(),
            body={"worker_id": worker["worker_id"], "parchi_id": worker["parchi_id"]},
        )
    )
    assert _body(after)["allowed"] is False
    assert _body(after)["policy_id"] == "assist-requires-live-consent"


# --------------------------------------------------------------------------- assistance


def test_assistance_is_denied_without_consent(monkeypatch):
    app, workers = _app_with_workers(consent_store=InMemoryConsentStore())
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    response = api_handler.handle(
        _event(
            "/api/assist",
            claims=_facilitator_claims(),
            body={"worker_id": worker["worker_id"], "parchi_id": worker["parchi_id"]},
        )
    )

    denied = _body(response)
    assert denied["allowed"] is False
    assert denied["policy_id"] == "assist-requires-live-consent"
    assert "view" not in denied


def test_assistance_is_denied_for_a_mismatched_worker(monkeypatch):
    app, workers = _app_with_workers(consent_store=InMemoryConsentStore())
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    first, second = workers[0], workers[1]
    app.grant_consent(first["parchi_id"], first["worker_id"])

    response = api_handler.handle(
        _event(
            "/api/assist",
            claims=_facilitator_claims(),
            body={"worker_id": second["worker_id"], "parchi_id": first["parchi_id"]},
        )
    )
    assert _body(response)["allowed"] is False


def test_assistance_is_denied_after_the_consent_expires():
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    worker = workers[0]
    # A grant minted two days ago and valid for an hour is already lapsed.
    app.grant_consent(
        worker["parchi_id"],
        worker["worker_id"],
        now=datetime.now(UTC) - timedelta(days=2),
    )

    denied = app.assist(
        worker_id=worker["worker_id"],
        parchi_id=worker["parchi_id"],
        principal=FACILITATOR,
    )
    assert denied["allowed"] is False
    assert denied["policy_id"] == "assist-requires-live-consent"


def test_the_facilitator_receives_only_the_redacted_view(monkeypatch):
    app, workers = _app_with_workers(consent_store=InMemoryConsentStore())
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]
    app.grant_consent(worker["parchi_id"], worker["worker_id"])

    response = api_handler.handle(
        _event(
            "/api/assist",
            claims=_facilitator_claims(),
            body={"worker_id": worker["worker_id"], "parchi_id": worker["parchi_id"]},
        )
    )
    allowed = _body(response)
    assert allowed["allowed"] is True
    assert set(allowed["view"]) == {
        "context_id",
        "parchi_id",
        "worker_id",
        "site_id",
        "claim_status",
        "consent_status",
        "consent_granted_at",
        "consent_expires_at",
    }
    text = json.dumps(allowed).lower()
    for banned in ("aadhaar", "bank", "phone", "ifsc", "obligation_ids", "source_quote"):
        assert banned not in text

    # Full Parchi disclosure stays denied: the facilitator screen reports a ViewParchi refusal.
    facilitator = api_handler.handle(
        _event("/api/facilitator", claims=_facilitator_claims(), method="GET")
    )
    read_attempt = _body(facilitator)["read_attempt"]
    assert read_attempt["allowed"] is False
    assert read_attempt["policy_id"] == "assist-is-not-disclosure"


# --------------------------------------------------------------------------- durability


def test_consent_persists_across_separate_application_instances():
    store = InMemoryConsentStore()
    first_app, workers = _app_with_workers(consent_store=store)
    worker = workers[0]
    first_app.grant_consent(worker["parchi_id"], worker["worker_id"])

    # A SEPARATE application instance, sharing only the consent store and the parchi store (a
    # fresh Lambda would share the DynamoDB tables, not the object graph).
    second_app = Demo(consent_store=store, store=first_app.store)

    resumed = second_app.assist(
        worker_id=worker["worker_id"],
        parchi_id=worker["parchi_id"],
        principal=FACILITATOR,
    )
    assert resumed["allowed"] is True
    assert resumed["view"]["consent_status"] == "granted"


def test_a_stale_grant_cannot_restore_a_revoked_consent_through_the_app():
    store = InMemoryConsentStore()
    app, workers = _app_with_workers(consent_store=store)
    worker = workers[0]
    grant = app.grant_consent(worker["parchi_id"], worker["worker_id"])
    observed = store.load(
        worker_id=worker["worker_id"],
        facilitator_id=FACILITATOR_ID,
        parchi_id=worker["parchi_id"],
    )
    assert observed is not None and observed.version == 1

    app.revoke_consent(grant["context_id"])

    # A grant formed before the revocation tries to land against the version it read.
    from aadesh_core.consent import grant_consent

    stale = grant_consent(
        context_id="ctx-stale",
        parchi_id=worker["parchi_id"],
        worker_id=worker["worker_id"],
        facilitator_id=FACILITATOR_ID,
        granted_at=datetime.now(UTC),
        ttl=timedelta(hours=12),
        actor_worker_id=worker["worker_id"],
    )
    with pytest.raises(ConsentStoreConflict):
        store.save(stale, expected_version=observed.version, actor_id=worker["worker_id"])

    denied = app.assist(
        worker_id=worker["worker_id"],
        parchi_id=worker["parchi_id"],
        principal=FACILITATOR,
    )
    assert denied["allowed"] is False


# --------------------------------------------------------------------------- fail closed


class _ExplodingConsentStore:
    """A consent store that is unreachable. Every read and write fails."""

    def find_live(self, **_kwargs):
        raise RuntimeError("consent store unreachable")

    def get(self, _context_id):
        raise RuntimeError("consent store unreachable")

    def load(self, **_kwargs):
        raise RuntimeError("consent store unreachable")

    def save(self, *_args, **_kwargs):
        raise RuntimeError("consent store unreachable")


def test_a_consent_store_failure_fails_closed_for_assistance():
    app, workers = _app_with_workers(consent_store=_ExplodingConsentStore())
    worker = workers[0]

    denied = app.assist(
        worker_id=worker["worker_id"],
        parchi_id=worker["parchi_id"],
        principal=FACILITATOR,
    )
    assert denied["allowed"] is False
    assert "view" not in denied

    # The facilitator screen likewise reports a denial rather than raising.
    payload = app.facilitator(principal=FACILITATOR)
    assert payload["assistance"]["allowed"] is False


def test_a_consent_store_failure_is_not_reported_as_a_successful_grant(monkeypatch):
    app, workers = _app_with_workers(consent_store=_ExplodingConsentStore())
    monkeypatch.setattr(api_handler, "build_application", lambda _config: app)
    worker = workers[0]

    response = api_handler.handle(
        _event(
            "/api/consent/grant",
            claims=_worker_claims(worker["worker_id"]),
            body={"parchi_id": worker["parchi_id"], "worker_id": worker["worker_id"]},
        )
    )

    assert response["statusCode"] != 200
    assert "consent_granted" not in _body(response)


def test_durable_assist_never_returns_a_view_it_could_not_read():
    """A store that raises must not be turned into an authorized response by any code path."""
    app, workers = _app_with_workers(consent_store=_ExplodingConsentStore())
    worker = workers[0]
    result = app.assist(
        worker_id=worker["worker_id"],
        parchi_id=worker["parchi_id"],
        principal=FACILITATOR,
    )
    assert result.get("view") is None
    assert result["allowed"] is False
