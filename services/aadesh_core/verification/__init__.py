"""Citation verification against hashed source bytes."""

from __future__ import annotations

from aadesh_core.verification.verifier import (
    CitationCheck,
    DocumentCheck,
    VerificationReport,
    normalise,
    verify_corpus,
)

__all__ = [
    "CitationCheck",
    "DocumentCheck",
    "VerificationReport",
    "normalise",
    "verify_corpus",
]
