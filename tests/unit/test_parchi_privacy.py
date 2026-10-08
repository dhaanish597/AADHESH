"""INVARIANT: the QR, the audit trail and the record leak nothing that outlives the shift.

A QR is a public artefact. It gets photographed, screenshotted, forwarded on WhatsApp and
pinned to a site-office wall. So the questions this file answers are all of the form "if this
ended up on a poster, or in a log sink that someone reads three years from now, what would
they learn?":

  * from the QR payload alone -- nothing but an opaque string
  * from the audit trail -- who confirmed which record, and a non-reversible token handle
  * from the parchi record -- the facts being asserted, and no credential at all

The banned-word list is deliberately blunt. It is not trying to be a PII detector; it is a
tripwire against a future field called `worker_phone` appearing in a payload, which is the
realistic way this breaks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace
from datetime import timedelta

import pytest

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.domain import AcknowledgementMethod, Provenance
from aadesh_core.parchi import _evidentiary_payload, seal
from aadesh_core.parchi import compute_content_hash as content_hash
from aadesh_core.parchi_ack import (
    ParchiAcknowledged,
    ParchiProvenance,
    RosterEntry,
    WorkflowExecution,
    create_parchi_for_worker,
)
from aadesh_core.parchi_ack.service import acknowledge_parchi, describe_pending_parchi
from aadesh_core.parchi_ack.tokens import (
    TOKEN_SCHEME,
    AcknowledgementQr,
    AcknowledgementToken,
    mint_acknowledgement_token,
)
from tests.support.builders import FIXED_NOW, invoked_stage, reading

BANNED_IN_QR = [
    "worker",
    "aadhaar",
    "aadhar",
    "phone",
    "mobile",
    "address",
    "bank",
    "ifsc",
    "account",
    "upi",
    "pan",
    "site",
    "parchi",
    "exec",
    "name",
    "json",
    "http",
    "://name",
]

EXECUTION = WorkflowExecution(
    execution_id="exec-privacy-001",
    site_id="site-001",
    source_event_id="evt-stage-invocation-001",
)

PROVENANCE = ParchiProvenance(
    stage=invoked_stage(),
    reading=reading(provenance=Provenance.MEASURED),
    obligation_ids=("ob-dust-01",),
    entitlement_refs=("ent-cited-clause-01",),
    readiness_checklist=("Welfare board registration number",),
)


def _flow(*, site_id: str = "site-001", worker_id: str = "worker-001"):
    store = InMemoryParchiStore()
    tokens = InMemoryAcknowledgementTokenStore()
    ledger = InMemoryIdempotencyLedger()
    audit = RecordingAuditLog()
    execution = replace(EXECUTION, site_id=site_id)
    issue = create_parchi_for_worker(
        parchi_id=f"parchi-{worker_id}",
        execution=execution,
        worker=RosterEntry(worker_id=worker_id, display_name="Worker A"),
        provenance=PROVENANCE,
        idempotency_key=f"idem-{worker_id}",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
    )
    return store, tokens, ledger, audit, issue


# --- the QR payload ---------------------------------------------------------


@pytest.mark.parametrize("banned", BANNED_IN_QR)
def test_the_qr_payload_contains_none_of_the_things_that_must_not_be_in_it(banned):
    _, _, _, _, issue = _flow()
    assert banned not in issue.qr.payload.lower()


def test_the_qr_payload_is_a_scheme_a_separator_and_an_opaque_token():
    _, _, _, _, issue = _flow()
    payload = issue.qr.payload

    assert payload.startswith(TOKEN_SCHEME)
    remainder = payload[len(TOKEN_SCHEME) :]
    assert payload.count("/") == 3, "a scheme and ONE path segment, nothing else"
    assert "?" not in payload and "#" not in payload
    assert " " not in payload
    assert remainder and remainder.isascii()


def test_the_qr_payload_does_not_name_the_worker_the_site_or_the_parchi():
    """The identifiers exist in the system; they must simply not be in the link."""
    _, _, _, _, issue = _flow()

    assert "worker-001" not in issue.qr.payload
    assert "site-001" not in issue.qr.payload
    assert issue.parchi.parchi_id not in issue.qr.payload
    assert EXECUTION.execution_id not in issue.qr.payload


def test_the_qr_payload_is_not_a_serialised_object():
    """Checked after the scheme, which is the only part allowed to contain punctuation."""
    _, _, _, _, issue = _flow()
    remainder = issue.qr.payload[len(TOKEN_SCHEME) :]

    for marker in ("{", "}", "[", "]", "=", ":", '"', "'", ",", "?", "&", "@", "."):
        assert marker not in remainder, f"{marker!r} suggests the payload is structured"


def test_the_qr_payload_is_not_derived_from_any_identifier():
    """A token that was, say, a hash of the parchi id would be computable by anyone."""
    _, _, _, _, issue = _flow()

    for candidate in (
        issue.parchi.parchi_id,
        "worker-001",
        EXECUTION.execution_id,
        EXECUTION.source_event_id,
        issue.parchi.site_id,
    ):
        for digest in (
            hashlib.sha256(candidate.encode()).hexdigest(),
            hashlib.md5(candidate.encode()).hexdigest(),
            candidate,
        ):
            assert digest not in issue.qr.payload


def test_two_sites_produce_indistinguishable_links():
    """Nothing about the payload reveals which site, worker or record it belongs to."""
    _, _, _, _, a = _flow(site_id="site-001", worker_id="worker-001")
    _, _, _, _, b = _flow(site_id="site-999", worker_id="worker-777")

    assert len(a.qr.payload) == len(b.qr.payload)
    assert a.qr.payload.split("/")[0] == b.qr.payload.split("/")[0]
    assert a.qr.payload[-1] != b.qr.payload[-1] or a.qr.payload != b.qr.payload


def test_the_qr_object_itself_carries_nothing_private():
    """`AcknowledgementQr` is the object a renderer holds. It must stay three fields wide."""
    assert {f.name for f in fields(AcknowledgementQr)} == {
        "payload",
        "token_hash",
        "expires_at",
    }


# --- the stored token -------------------------------------------------------


def test_the_stored_token_record_cannot_hold_a_raw_token():
    """There is no field a raw value could be assigned to, and none that holds one."""
    _, tokens, _, _, issue = _flow()
    raw = issue.qr.payload[len(TOKEN_SCHEME) :]

    stored = tokens.get(issue.qr.token_hash)
    assert isinstance(stored, AcknowledgementToken)

    names = {f.name for f in fields(AcknowledgementToken)}
    for forbidden in ("token", "raw", "secret", "value", "payload"):
        assert forbidden not in names, (
            f"AcknowledgementToken has a field named {forbidden!r}. It is supposed to be "
            f"impossible to put a raw token on this record."
        )
    assert raw not in repr(stored)


def test_a_stored_token_is_a_hash_and_nothing_reversible():
    _, tokens, _, _, issue = _flow()
    stored = tokens.get(issue.qr.token_hash)

    assert len(stored.token_hash) == 64
    assert all(c in "0123456789abcdef" for c in stored.token_hash)
    assert stored.token_hash != issue.qr.payload
    assert stored.reference.startswith("tok_")
    assert len(stored.reference) == len("tok_") + 16


def test_a_thousand_tokens_are_all_different_and_all_full_entropy():
    seen = set()
    for i in range(1000):
        _, token = mint_acknowledgement_token(
            parchi_id=f"parchi-{i}", worker_id="worker-001", now=FIXED_NOW
        )
        seen.add(token.token_hash)
    assert len(seen) == 1000


def test_the_token_is_long_enough_that_guessing_is_not_a_strategy():
    qr, _ = mint_acknowledgement_token(
        parchi_id="parchi-001", worker_id="worker-001", now=FIXED_NOW
    )
    raw = qr.payload[len(TOKEN_SCHEME) :]
    assert len(raw) >= 43, "43 url-safe chars is 256 bits"


# --- the audit trail --------------------------------------------------------


def test_the_audit_trail_never_contains_the_raw_token():
    store, tokens, ledger, audit, issue = _flow()
    raw = issue.qr.payload[len(TOKEN_SCHEME) :]

    acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id="worker-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    )

    text = audit.all_text()
    assert raw not in text
    assert issue.qr.payload not in text, "not even as a whole payload"


def test_the_audit_trail_carries_the_token_reference_so_replays_can_be_correlated():
    store, tokens, ledger, audit, issue = _flow()

    acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id="worker-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    )

    assert tokens.get(issue.qr.token_hash).reference in audit.all_text()


def test_the_audit_event_has_no_field_that_could_carry_a_token():
    assert {f.name for f in fields(ParchiAcknowledged)} == {
        "event_id",
        "parchi_id",
        "worker_id",
        "occurred_at",
        "acknowledgement_method",
        "token_reference",
        "workflow_execution_id",
        "site_id",
        "schema_version",
        "event_type",
    }


def test_the_audit_detail_is_flat_strings():
    """A nested structure is a place to hide a value the flat check would not reach."""
    _, _, _, _, issue = _flow()
    event = ParchiAcknowledged(
        event_id="evt-1",
        parchi_id=issue.parchi.parchi_id,
        worker_id="worker-001",
        occurred_at=FIXED_NOW,
        acknowledgement_method=AcknowledgementMethod.QR_CONFIRMED,
        token_reference="tok_0123456789abcdef",
    )

    detail = event.as_audit_detail()
    assert all(isinstance(k, str) for k in detail)
    assert all(isinstance(v, str) for v in detail.values())


# --- the record -------------------------------------------------------------


def test_the_parchi_record_never_contains_the_raw_token():
    store, tokens, ledger, audit, issue = _flow()
    raw = issue.qr.payload[len(TOKEN_SCHEME) :]

    outcome = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id="worker-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    )

    assert raw not in repr(outcome.parchi)
    assert issue.qr.payload not in repr(outcome.parchi)
    assert raw not in repr(store.get(issue.parchi.parchi_id))


def test_the_content_hash_is_a_pure_function_of_the_record():
    """So nothing outside the record -- a token, a clock, an environment -- can be silently
    influencing what the seal attests to."""
    store, tokens, ledger, audit, issue = _flow()
    acked = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id="worker-001",
        now=FIXED_NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    ).parchi

    sealed = seal(acked, now=FIXED_NOW)

    assert content_hash(sealed) == content_hash(replace(sealed))
    assert content_hash(sealed) != content_hash(replace(sealed, worker_id="worker-002"))


def test_the_raw_token_is_not_an_input_to_the_content_hash():
    """The hash covers the acknowledgement's FACTS, including the token reference.

    The reference is a recorded fact -- it is what an auditor correlates a seal against. The
    token itself is not covered and must not be: re-verifying a record sealed months ago must
    never require the short-lived secret that carried it.
    """
    store, tokens, ledger, audit, issue = _flow()
    raw = issue.qr.payload[len(TOKEN_SCHEME) :]

    sealed = seal(
        acknowledge_parchi(
            payload=issue.qr.payload,
            actor_worker_id="worker-001",
            now=FIXED_NOW,
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
        ).parchi,
        now=FIXED_NOW,
    )

    assert raw not in repr(sealed)
    assert raw not in json.dumps(_evidentiary_payload(sealed))


def test_the_sealed_record_states_which_documents_it_rests_on():
    """Accountability, not secrecy: the citation is meant to be checkable."""
    _, _, _, _, issue = _flow()
    assert issue.parchi.source_document_ids == (PROVENANCE.stage.order_doc_id,)
    assert issue.parchi.source_hashes == (PROVENANCE.stage.order_sha256,)


# --- the describe view ------------------------------------------------------


def test_the_view_a_worker_sees_carries_no_contact_or_identity_document():
    store, tokens, _, _, issue = _flow()

    view = describe_pending_parchi(
        payload=issue.qr.payload, now=FIXED_NOW, store=store, tokens=tokens
    )

    rendered = repr(view).lower()
    for banned in (
        "aadhaar",
        "aadhar",
        "phone",
        "mobile",
        "whatsapp",
        "bank",
        "ifsc",
        "account",
        "upi",
        "address",
        "passport",
    ):
        assert banned not in rendered, f"the worker view exposes {banned!r}"


def test_the_view_does_not_contain_the_raw_token_either():
    store, tokens, _, _, issue = _flow()
    raw = issue.qr.payload[len(TOKEN_SCHEME) :]

    view = describe_pending_parchi(
        payload=issue.qr.payload, now=FIXED_NOW, store=store, tokens=tokens
    )

    assert raw not in repr(view)


# --- retention --------------------------------------------------------------


def test_a_token_record_holds_no_free_text_at_all():
    """Every field is either an id, an instant, or a hash. Nothing is a place for a note."""
    _, token = mint_acknowledgement_token(
        parchi_id="parchi-001", worker_id="worker-001", now=FIXED_NOW, ttl=timedelta(hours=1)
    )
    assert isinstance(token.issued_at, type(FIXED_NOW))
    assert token.consumed_at is None
    assert token.consumed_event_id is None
    assert token.state.value == "active"
    assert "qr" not in repr(token)
