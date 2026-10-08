"""INVARIANT: the authorization layer learns who may act, and nothing about who anyone is.

A Cedar entity store is not a private place. It is serialised into the request, printed in
engine diagnostics, captured in traces, and read by whoever writes policy -- which is a wider
group than whoever may read a worker's record. So the rule this file enforces is narrower than
"no PII anywhere": it is that **nothing the authorizer is given, and nothing it says back, is
anything other than an id, a state, a site or an instant.**

Three distinct surfaces, checked separately because they leak differently:

  * **The entities** -- what crosses into the engine. A `worker_phone` attribute here would sit
    in every policy trace forever.
  * **The decision copy** -- what comes back out. `AuthorizationDenied` is shown to a caller, so
    it must not name which record was reached for, or which worker holds it.
  * **The audit trail** -- what outlives the request. A boundary-run acknowledgement must add
    no credential and no contact detail to what Prompt 5 already recorded.

The facilitator case gets its own test, because the temptation there is real and structural: a
facilitator helping with a claim is the one actor who would find the whole record convenient.
"""

from __future__ import annotations

import contextlib
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.authorization.resources import (
    claim_assistance_resource,
    parchi_resource,
    site_resource,
)
from aadesh_core.authorization.service import AuthorizationService
from aadesh_core.consent import ClaimAssistanceContext, grant_consent
from aadesh_core.errors import AuthorizationDenied
from aadesh_core.parchi_ack import ParchiProvenance, RosterEntry, WorkflowExecution
from aadesh_core.parchi_ack.tokens import TOKEN_SCHEME
from aadesh_core.parchi_ack.workflow import create_parchi_for_worker
from aadesh_core.ports.authz import EntityRef
from tests.support.authz_builders import facilitator, supervisor, worker

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
SITE = "site-001"

#: Deliberately blunt. This is not a PII detector; it is a tripwire against a future attribute
#: called `worker_phone` or `aadhaar_ref` appearing in an entity, which is the realistic way
#: this breaks -- someone adds a field to make a policy easier to write.
BANNED_KEYS = {
    "name",
    "display_name",
    "full_name",
    "phone",
    "mobile",
    "whatsapp",
    "contact",
    "aadhaar",
    "aadhar",
    "uid",
    "pan",
    "passport",
    "address",
    "bank",
    "account",
    "ifsc",
    "upi",
    "salary",
    "wage",
    "amount",
    "health",
    "caste",
    "religion",
    "dob",
    "date_of_birth",
    "email",
}

BANNED_IN_TEXT = (
    "aadhaar",
    "aadhar",
    "phone",
    "mobile",
    "whatsapp",
    "bank",
    "ifsc",
    "upi",
    "account number",
    "passport",
    "salary",
    "wage",
)


@pytest.fixture(scope="module")
def cedar(repo_root) -> CedarAuthorizationProvider:
    return CedarAuthorizationProvider(
        policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
        denials_path=repo_root / "infra" / "cedar" / "denials.json",
        schema_path=repo_root / "infra" / "cedar" / "schema.cedarschema.json",
    )


@pytest.fixture
def service(cedar) -> AuthorizationService:
    return AuthorizationService(authz=cedar)


def _open_parchi(*, worker_id="wrk-1", site_id=SITE):
    store = InMemoryParchiStore()
    tokens = InMemoryAcknowledgementTokenStore()
    execution = WorkflowExecution(
        execution_id="exec-privacy", site_id=site_id, source_event_id="evt-privacy"
    )
    issue = create_parchi_for_worker(
        parchi_id=f"parchi-{worker_id}",
        execution=execution,
        worker=RosterEntry(worker_id=worker_id, display_name="Worker A"),
        provenance=ParchiProvenance(stage=None, reading=None),
        idempotency_key=f"idem-{worker_id}",
        now=NOW,
        store=store,
        tokens=tokens,
    )
    return store, tokens, issue


def _consent(**overrides) -> ClaimAssistanceContext:
    fields_ = dict(
        context_id="ctx-1",
        parchi_id="parchi-wrk-1",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        granted_at=NOW,
        ttl=timedelta(hours=24),
    )
    fields_.update(overrides)
    return grant_consent(**fields_)


def _store_for(cedar, principal, resource) -> list[dict]:
    """The entity array the adapter would hand Cedar, exactly as it would be serialised."""
    return cedar._entities(principal, resource)


# ---------------------------------------------------------------------------
# What crosses into the engine
# ---------------------------------------------------------------------------


def test_a_parchi_reaches_the_engine_as_four_things_and_no_more(cedar):
    _, _, issue = _open_parchi()
    entities = _store_for(cedar, worker("wrk-1"), parchi_resource(issue.parchi))
    parchi_entity = next(e for e in entities if "Parchi" in e["uid"]["type"])

    assert set(parchi_entity["attrs"]) == {"worker", "siteId", "state", "execution"}


def test_a_claim_context_reaches_the_engine_as_six_things(cedar):
    entities = _store_for(cedar, facilitator("fac-1"), claim_assistance_resource(_consent()))
    context_entity = next(e for e in entities if "ClaimAssistanceContext" in e["uid"]["type"])

    assert set(context_entity["attrs"]) == {
        "worker",
        "facilitator",
        "parchi",
        "consentGranted",
        "grantedAt",
        "expiresAt",
    }


def test_no_entity_attribute_is_named_after_a_personal_fact(cedar):
    """Across every entity in a full request -- the principal, the resource, and every entity
    referenced by an attribute."""
    requests = [
        (supervisor("sup-1", site=SITE), site_resource(SITE)),
        (worker("wrk-1"), parchi_resource(_open_parchi()[2].parchi)),
        (facilitator("fac-1"), claim_assistance_resource(_consent())),
    ]
    for principal, resource in requests:
        for entity in _store_for(cedar, principal, resource):
            for key in entity["attrs"]:
                assert key.lower() not in BANNED_KEYS, (
                    f"{entity['uid']['type']} carries an attribute named {key!r}. The "
                    f"authorizer is given identifiers, states, sites and instants -- nothing "
                    f"about who a person is."
                )


def test_no_entity_attribute_value_is_anything_but_an_id_a_state_or_an_instant(cedar):
    """A value's TYPE is as telling as its name. A free-form string is where a phone number
    ends up when nobody decided to put one there."""
    requests = [
        (supervisor("sup-1", site=SITE), site_resource(SITE)),
        (worker("wrk-1"), parchi_resource(_open_parchi()[2].parchi)),
        (facilitator("fac-1"), claim_assistance_resource(_consent())),
    ]
    for principal, resource in requests:
        for entity in _store_for(cedar, principal, resource):
            for key, value in entity["attrs"].items():
                assert isinstance(value, (str, int, float, bool, dict)), (key, type(value))
                if isinstance(value, str):
                    # Ids and state names are short; nothing descriptive is.
                    assert len(value) <= 64, f"{key} looks like prose, not an identifier"


def test_a_referenced_entity_is_a_bare_reference_with_no_attributes(cedar):
    """`Parchi.worker` must be a pointer, not an embedded copy of the worker. An embedded
    entity is where a name or a contact detail would ride along unnoticed.

    The acting principal here is deliberately NOT the worker named on the record, so the two
    entities are genuinely distinct and the referenced one can be inspected on its own. (When
    they are the same person the adapter adds one entity, not two -- which is correct, and
    would have made this test pass by comparing a thing to itself.)
    """
    _, _, issue = _open_parchi(worker_id="wrk-1")
    entities = _store_for(cedar, facilitator("fac-1"), parchi_resource(issue.parchi))

    principals = [e for e in entities if e["uid"]["type"].endswith("::Principal")]
    assert {e["uid"]["id"] for e in principals} == {"fac-1", "wrk-1"}

    named_worker = next(e for e in principals if e["uid"]["id"] == "wrk-1")
    assert named_worker["attrs"] == {}, (
        "the worker named on a parchi must be referenced with NO attributes"
    )


def test_the_principal_entity_carries_a_role_and_a_site_and_nothing_else(cedar):
    entities = _store_for(cedar, supervisor("sup-1", site=SITE), site_resource(SITE))
    principal = next(e for e in entities if e["uid"]["type"].endswith("::Principal"))

    assert set(principal["attrs"]) == {"role", "assignedSite"}


# ---------------------------------------------------------------------------
# The facilitator: assistance without disclosure
# ---------------------------------------------------------------------------


def test_assistance_is_authorized_against_a_reference_not_the_record(cedar):
    """The resource is a `ClaimAssistanceContext` whose `parchi` attribute is a POINTER.

    This is what makes "a facilitator may assist but not read" structural rather than a rule
    someone has to remember: there is no parchi content in the request to disclose."""
    resource = claim_assistance_resource(_consent())
    assert resource.entity_type == "ClaimAssistanceContext"
    assert isinstance(resource.attributes["parchi"], EntityRef)
    assert not isinstance(resource.attributes["parchi"], str), "an id string would be read as prose"

    entities = _store_for(cedar, facilitator("fac-1"), resource)
    parchi_entities = [e for e in entities if e["uid"]["type"].endswith("::Parchi")]
    assert len(parchi_entities) == 1
    assert parchi_entities[0]["attrs"] == {}, (
        "the parchi referenced by a consent must carry no attributes into the request"
    )


def test_a_live_consent_authorizes_assistance_without_naming_the_worker(cedar):
    decision = cedar.authorize(
        principal=facilitator("fac-1"),
        action="AssistClaim",
        resource=claim_assistance_resource(_consent()),
        context={"now": int(NOW.timestamp())},
    )
    assert decision.allowed is True
    for banned in BANNED_IN_TEXT:
        assert banned not in decision.reason.lower()


# ---------------------------------------------------------------------------
# What comes back out
# ---------------------------------------------------------------------------


def test_a_denial_shown_to_a_caller_names_no_record_and_no_person(service):
    """The sentence is one line, identical for every refusal. A caller who could read out of it
    WHICH parchi was reached for, or WHOSE, would have a probe for what exists."""
    _, _, issue = _open_parchi(worker_id="wrk-1")
    with pytest.raises(AuthorizationDenied) as denied:
        service.require_view_parchi(principal=facilitator("fac-1"), parchi=issue.parchi, now=NOW)

    sentence = str(denied.value)
    assert sentence == "You do not have permission to perform this action."
    assert issue.parchi.parchi_id not in sentence
    assert "wrk-1" not in sentence
    assert "site-001" not in sentence
    for banned in BANNED_IN_TEXT:
        assert banned not in sentence.lower()


def test_a_denial_carries_the_policy_id_for_operators_and_not_for_callers(service):
    """The split that makes a denial both debuggable and safe: the reason is on the exception
    OBJECT, and nowhere in the text a caller sees."""
    _, _, issue = _open_parchi()
    with pytest.raises(AuthorizationDenied) as denied:
        service.require_view_parchi(principal=facilitator("fac-1"), parchi=issue.parchi, now=NOW)

    assert denied.value.decision.policy_id == "assist-is-not-disclosure"
    assert denied.value.decision.policy_id not in str(denied.value)


# ---------------------------------------------------------------------------
# What outlives the request
# ---------------------------------------------------------------------------


def test_the_audit_trail_from_a_boundary_run_gains_no_credential_and_no_contact_detail(service):
    """Prompt 5 already established what an acknowledgement records. Running it THROUGH the
    authorization boundary must not add to that: no raw token, and nothing about a person."""
    store, tokens, issue = _open_parchi(worker_id="wrk-1")
    ledger = InMemoryIdempotencyLedger()
    audit = RecordingAuditLog()
    raw = issue.qr.payload[len(TOKEN_SCHEME) :]

    service.acknowledge_own_parchi(
        principal=worker("wrk-1"),
        payload=issue.qr.payload,
        now=NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    )

    text = audit.all_text()
    assert raw not in text, "the boundary must not start recording the credential"
    assert issue.qr.payload not in text
    for banned in BANNED_IN_TEXT:
        assert banned not in text.lower()


def test_the_boundary_records_nothing_of_its_own(service):
    """No audit event, no log line, no counter. Authorization decides; the domain records. A
    second trail written by the boundary would be a second place to keep consistent -- and a
    second place for a record's contents to end up."""
    _, _, issue = _open_parchi(worker_id="wrk-1")
    audit = RecordingAuditLog()

    with contextlib.suppress(AuthorizationDenied):
        service.require_view_parchi(principal=facilitator("fac-1"), parchi=issue.parchi, now=NOW)

    assert audit.records == [], (
        "authorization wrote to the audit log. The trail belongs to the domain, which records "
        "facts; a decision is not a fact about the world, it is how one was reached."
    )


# ---------------------------------------------------------------------------
# The consent record itself
# ---------------------------------------------------------------------------


def test_a_consent_record_has_nowhere_to_put_a_personal_detail():
    """Asserted on the FIELD SET, so adding a field is a failing test rather than a quiet
    widening of what the facilitator boundary carries."""
    assert {f.name for f in fields(ClaimAssistanceContext)} == {
        "context_id",
        "parchi_id",
        "worker_id",
        "facilitator_id",
        "granted_at",
        "expires_at",
        "consent_granted",
        "revoked_at",
    }


def test_a_consent_renders_no_personal_detail():
    rendered = repr(_consent()).lower()
    for banned in BANNED_IN_TEXT:
        assert banned not in rendered
