"""Verification port.

`SourceBytesCitationVerifier` (the default, zero-infra) is implemented in
`aadesh_core.verification`. An OpenSearch-backed verifier satisfying the same port is the
opt-in `--with-index` path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from aadesh_core.verification import VerificationReport


@runtime_checkable
class CitationVerifier(Protocol):
    def verify(self, corpus_root: Path) -> VerificationReport:
        """Re-prove every citation. MUST NOT mutate the corpus."""
        ...
