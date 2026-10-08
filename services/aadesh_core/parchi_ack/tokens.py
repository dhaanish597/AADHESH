"""Opaque, short-lived, single-purpose acknowledgement tokens, and the QR payload built on them.

The design constraint that shapes this whole module: **a QR is a public artefact.** It gets
photographed, screenshotted, forwarded and pinned to a noticeboard. So the payload is
`aadesh://ack/<random>` and carries nothing else -- no worker id, no parchi id, no site, no
JSON, no counter. Everything the token means is resolved server-side from the hash.

Three consequences worth stating plainly, because each is a property someone will be tempted
to break later:

  * **The raw token is stored nowhere.** `mint_acknowledgement_token` returns it once, inside
    the displayable payload, and returns a record holding only `sha256`. A stolen database
    therefore yields no usable tokens. `AcknowledgementToken` has no field that could hold
    the raw value.
  * **The token is a bearer credential, so it must be unguessable.** 32 bytes from `secrets`,
    not a counter and not a hash of the ids -- `token_urlsafe(32)` gives 256 bits over a
    64-character alphabet.
  * **Rejection is uniform.** Every malformed payload produces the same `TokenRejected` with
    the same sentence; the reason is a separate field the API layer must not render.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from aadesh_core.domain import AcknowledgementMethod
from aadesh_core.errors import TokenRejected, TokenRejectionReason

# Re-exported so callers get the rejection vocabulary from the module that raises it.
__all__ = [
    "DEFAULT_TOKEN_TTL",
    "TOKEN_SCHEME",
    "AcknowledgementMethod",
    "AcknowledgementQr",
    "AcknowledgementToken",
    "TokenRejectionReason",
    "TokenState",
    "hash_token",
    "mint_acknowledgement_token",
    "parse_acknowledgement_payload",
    "token_reference",
]

TOKEN_SCHEME = "aadesh://ack/"
"""The only payload shape this system issues or accepts."""

DEFAULT_TOKEN_TTL = timedelta(hours=24)
"""Long enough that a worker who finishes a shift and opens the link the next morning still
gets in; short enough that a forwarded screenshot stops working the day after."""

_ENTROPY_BYTES = 32
"""256 bits. `token_urlsafe(32)` renders as 43 url-safe characters."""

_MIN_TOKEN_CHARS = 43
"""Refuse anything shorter than a full-entropy token rather than looking it up. A short token
cannot be one of ours, so a lookup would only ever be a probing oracle."""

_MAX_TOKEN_CHARS = 128
"""An upper bound so a megabyte of junk cannot be hashed into the ledger."""

_URL_SAFE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


class TokenState(StrEnum):
    """ACTIVE until used, CONSUMED forever after.

    There is no third state and no way back: a token that could return to ACTIVE would make
    "used tokens cannot be replayed" untrue.
    """

    ACTIVE = "active"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class AcknowledgementToken:
    """The STORABLE half of a minted token. Holds a hash, never the token itself.

    Note what is absent: there is no `token`, `secret`, `raw` or `value` field, so there is
    no shape a careless caller could serialise into a log line. Compare `token_hash` to an
    incoming token to find this record; that is the only operation it supports.
    """

    token_hash: str
    parchi_id: str
    worker_id: str
    issued_at: datetime
    expires_at: datetime
    state: str = TokenState.ACTIVE
    consumed_at: datetime | None = None
    consumed_event_id: str | None = None

    def is_expired(self, now: datetime) -> bool:
        """True at and after `expires_at`. The boundary is exclusive so a ttl of exactly
        zero is already expired rather than valid for an instant."""
        return now >= self.expires_at

    @property
    def reference(self) -> str:
        """A short handle for audit correlation and for explaining "which link" to a user.

        Derived from the hash, so it is stable, non-reversible and safe to keep forever.
        """
        return token_reference(self.token_hash)


@dataclass(frozen=True, slots=True)
class AcknowledgementQr:
    """What gets rendered as a QR code: a string, and the facts the UI needs to caption it.

    `payload` is public by construction. Do not add fields to this class without asking
    whether they would be acceptable on a poster in a site office.
    """

    payload: str
    token_hash: str
    expires_at: datetime


def hash_token(raw_token: str) -> str:
    """SHA-256 of the raw token, hex. Plain hashing is right here where a password would need
    a KDF: the input is 256 bits of uniform randomness, so there is no dictionary to run."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def token_reference(token_hash: str) -> str:
    """The public handle for a token: `tok_` plus the first 16 hex characters."""
    return f"tok_{token_hash[:16]}"


def mint_acknowledgement_token(
    *,
    parchi_id: str,
    worker_id: str,
    now: datetime,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
) -> tuple[AcknowledgementQr, AcknowledgementToken]:
    """Mint one token for one parchi and one worker.

    Returns `(qr, token)`: hand `qr` to whoever renders it, store `token`. The raw value
    exists only on the way back up this stack frame and is deliberately not recoverable
    afterwards -- which is why a replay of a creation request gets NO token rather than a
    second copy of the first one.
    """
    raw = secrets.token_urlsafe(_ENTROPY_BYTES)
    token_hash = hash_token(raw)

    token = AcknowledgementToken(
        token_hash=token_hash,
        parchi_id=parchi_id,
        worker_id=worker_id,
        issued_at=now,
        expires_at=now + ttl,
    )
    qr = AcknowledgementQr(
        payload=f"{TOKEN_SCHEME}{raw}",
        token_hash=token_hash,
        expires_at=token.expires_at,
    )
    return qr, token


def parse_acknowledgement_payload(payload: str) -> str:
    """Extract the opaque token from a scanned payload, or refuse it.

    Refusal is total and uniform. Every branch raises the same `TokenRejected(MALFORMED)`,
    so a caller cannot use this function to ask "is this shape close to valid?".
    """
    if not isinstance(payload, str):
        raise TokenRejected(TokenRejectionReason.MALFORMED)

    candidate = payload.strip()

    if not candidate.startswith(TOKEN_SCHEME):
        raise TokenRejected(TokenRejectionReason.MALFORMED)

    remainder = candidate[len(TOKEN_SCHEME) :]

    # Exactly one path segment: no extra slashes, no traversal, no query, no fragment.
    if not remainder or "/" in remainder:
        raise TokenRejected(TokenRejectionReason.MALFORMED)

    if not (_MIN_TOKEN_CHARS <= len(remainder) <= _MAX_TOKEN_CHARS):
        raise TokenRejected(TokenRejectionReason.MALFORMED)

    if not _URL_SAFE.match(remainder):
        raise TokenRejected(TokenRejectionReason.MALFORMED)

    return remainder
