"""INVARIANT: the QR carries an opaque handle and nothing else.

A parchi QR gets photographed, screenshotted, forwarded on WhatsApp and pinned to a site
noticeboard. Anything in that payload is public. So the payload is
`aadesh://ack/<random>` and nothing more: no worker id, no site id, no name, no JSON blob,
no sequential number anybody could walk.

The properties asserted here are the ones that make that claim testable rather than
aspirational:

  * unpredictable  -- two mints for the SAME parchi and worker must not collide
  * opaque         -- the payload must not contain the worker, the parchi or the site
  * short-lived    -- an expiry that a caller cannot forget to set
  * single-purpose -- it resolves to one parchi and one worker, and says nothing else
  * fail-safe      -- malformed and expired input is refused, never guessed at
"""

from __future__ import annotations

import base64
import re
from datetime import timedelta

import pytest

from aadesh_core.errors import TokenRejected
from aadesh_core.parchi_ack.tokens import (
    DEFAULT_TOKEN_TTL,
    TOKEN_SCHEME,
    AcknowledgementToken,
    TokenRejectionReason,
    TokenState,
    hash_token,
    mint_acknowledgement_token,
    parse_acknowledgement_payload,
)
from tests.support.builders import FIXED_NOW

LATER = FIXED_NOW + timedelta(hours=1)
WAY_LATER = FIXED_NOW + timedelta(days=30)


def a_mint(**over):
    return mint_acknowledgement_token(
        parchi_id=over.get("parchi_id", "parchi-001"),
        worker_id=over.get("worker_id", "worker-001"),
        now=over.get("now", FIXED_NOW),
        ttl=over.get("ttl", DEFAULT_TOKEN_TTL),
    )


# --- minting ---------------------------------------------------------------


def test_minting_returns_a_displayable_qr_and_a_storable_record():
    qr, token = a_mint()
    assert qr.payload.startswith(TOKEN_SCHEME)
    assert isinstance(token, AcknowledgementToken)
    assert token.state is TokenState.ACTIVE


def test_the_stored_record_holds_only_a_hash_of_the_token():
    """The raw token is handed out for display exactly once and never stored."""
    qr, token = a_mint()
    raw = parse_acknowledgement_payload(qr.payload)

    assert raw not in token.token_hash
    assert token.token_hash == hash_token(raw)
    assert len(token.token_hash) == 64


def test_the_token_is_bound_to_one_parchi_and_one_worker():
    _, token = a_mint(parchi_id="parchi-007", worker_id="worker-042")
    assert token.parchi_id == "parchi-007"
    assert token.worker_id == "worker-042"


def test_the_token_has_an_expiry():
    _, token = a_mint(ttl=timedelta(hours=24))
    assert token.expires_at == FIXED_NOW + timedelta(hours=24)


# --- unpredictability ------------------------------------------------------


def test_two_tokens_for_the_same_parchi_and_worker_never_collide():
    """The single most important property. A counter would fail this immediately."""
    raw = {parse_acknowledgement_payload(a_mint()[0].payload) for _ in range(1000)}
    assert len(raw) == 1000


def test_the_token_is_not_derived_from_the_ids_it_is_bound_to():
    qr, token = a_mint(parchi_id="parchi-001", worker_id="worker-001")
    raw = parse_acknowledgement_payload(qr.payload)

    for identifier in (token.parchi_id, token.worker_id, "site-001"):
        assert identifier not in raw
        assert identifier not in qr.payload


def test_the_token_carries_at_least_256_bits_of_url_safe_entropy():
    raw = parse_acknowledgement_payload(a_mint()[0].payload)

    assert re.fullmatch(r"[A-Za-z0-9_-]+", raw), "must be url-safe base64 with no padding"
    # 32 random bytes -> 43 url-safe chars. Anything shorter is guessable enough to matter.
    assert len(raw) >= 43
    assert len(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))) >= 32


# --- opacity: no PII, no site, no structure --------------------------------


def test_the_payload_is_a_scheme_and_a_token_and_nothing_else():
    qr, _ = a_mint()
    assert qr.payload.count("/") == 3, "aadesh://ack/<token>: exactly three slashes"
    assert "?" not in qr.payload, "no query string -- a query would be a place to hide data"
    assert "#" not in qr.payload, "no fragment"
    assert qr.payload.split(TOKEN_SCHEME)[1] == parse_acknowledgement_payload(qr.payload)


def test_the_payload_is_not_json():
    qr, _ = a_mint()
    assert not qr.payload.lstrip().startswith(("{", "["))


@pytest.mark.parametrize(
    "pii",
    [
        "worker-001",
        "parchi-001",
        "site-001",
        "Aadhaar",
        "aadhaar",
        "9876543210",
        "account",
        "bank",
        "ifsc",
        "phone",
        "address",
        "display_name",
        "Ramesh",
    ],
)
def test_the_payload_contains_no_pii_and_no_field_names(pii):
    qr, _ = a_mint()
    assert pii.lower() not in qr.payload.lower()


def test_two_sites_produce_indistinguishable_payloads():
    """Nothing in the payload betrays WHICH parchi or site it belongs to.

    A reader holding two QRs from two different sites cannot tell them apart, which is the
    whole point of an opaque handle.
    """
    a, _ = a_mint(parchi_id="parchi-a", worker_id="worker-a")
    b, _ = a_mint(parchi_id="parchi-b", worker_id="worker-b")

    assert a.payload[: len(TOKEN_SCHEME)] == b.payload[: len(TOKEN_SCHEME)]
    assert len(a.payload) == len(b.payload)


# --- single-purpose reference for audit ------------------------------------


def test_the_audit_reference_is_derived_from_the_hash_not_the_token():
    qr, token = a_mint()
    raw = parse_acknowledgement_payload(qr.payload)

    assert raw not in token.reference
    assert token.token_hash[:16] in token.reference


# --- expiry ----------------------------------------------------------------


def test_a_fresh_token_is_not_expired():
    _, token = a_mint()
    assert token.is_expired(LATER) is False


def test_a_token_expires():
    _, token = a_mint()
    assert token.is_expired(WAY_LATER) is True


def test_the_expiry_boundary_is_exclusive():
    _, token = a_mint(ttl=timedelta(hours=1))
    assert token.is_expired(token.expires_at) is True
    assert token.is_expired(token.expires_at - timedelta(seconds=1)) is False


# --- malformed input fails safely ------------------------------------------


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "   ",
        "not-a-uri",
        "https://example.com/ack/abc",
        "aadesh://ack",
        "aadesh://ack/",
        "aadesh://ack/short",
        "aadesh://ack/" + "a" * 43 + "/extra",
        "aadesh://view/" + "a" * 43,
        "javascript:alert(1)",
        "aadesh://ack/" + "../../etc/passwd",
        "aadesh://ack/" + "a" * 43 + "\x00",
        "aadesh://ack/" + "!" * 43,
        '{"parchi_id": "parchi-001"}',
        "aadesh://ack/🙂🙂🙂",
    ],
)
def test_malformed_payloads_are_refused(garbage):
    with pytest.raises(TokenRejected) as exc:
        parse_acknowledgement_payload(garbage)
    assert exc.value.reason is TokenRejectionReason.MALFORMED


def test_a_refused_payload_does_not_leak_what_was_wrong_with_it():
    """The user-facing sentence is the same for every rejection.

    Distinguishing "that token never existed" from "that token expired" tells a prober which
    guesses were close. The reason code is available to the domain; the sentence is not
    allowed to vary.
    """
    sentences = set()
    for garbage in ("", "aadesh://ack/short", "https://evil.example/", "aadesh://view/" + "a" * 43):
        with pytest.raises(TokenRejected) as exc:
            parse_acknowledgement_payload(garbage)
        sentences.add(exc.value.message)

    assert len(sentences) == 1


def test_a_valid_payload_round_trips():
    qr, token = a_mint()
    assert hash_token(parse_acknowledgement_payload(qr.payload)) == token.token_hash
