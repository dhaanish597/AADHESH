"""Turning downloaded document bytes into citable page text.

This is the boundary where the most common ingestion mistake happens: hashing and storing
*something that is not the order*. A saved HTML page, a news article about the order, or a
hand-written summary all have plausible filenames and none of them are law. So the very first
check is the PDF magic number, and the second is that there is real text to quote from -- a
scan with no text layer is accepted by neither the hash check nor a human reviewer.

pypdf is imported lazily. `make verify` must never require it: verification re-reads the
extracted `pN.txt` files, which are committed, so the central proof stays zero-infra.
"""

from __future__ import annotations

import io
from pathlib import Path

from aadesh_core.errors import AadeshError

PDF_MAGIC = b"%PDF-"

INSTALL_HINT = "pip install -e '.[ingest]'"


class SourceExtractionError(AadeshError):
    """The bytes could not be turned into citable text."""


def extract_pages(data: bytes) -> list[str]:
    """One string per page, 1-indexed by position. Raises rather than returning an empty list."""
    if not data.startswith(PDF_MAGIC):
        raise SourceExtractionError(
            "these bytes do not begin with %PDF-. An HTML page saved under a .pdf name, a "
            "news article about the order, or your own summary of the order, is not the "
            "order. Download the PDF itself from the official domain."
        )

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on the local install
        raise SourceExtractionError(
            f"pypdf is required to ingest a PDF and is not installed. Run: {INSTALL_HINT}"
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise SourceExtractionError(f"the PDF could not be read: {exc}") from exc

    if not pages:
        raise SourceExtractionError("the PDF reports zero pages")

    if not any(page.strip() for page in pages):
        raise SourceExtractionError(
            "the PDF has no extractable text. It is probably a scan with no text layer, and a "
            "quote cannot be proved against pixels. Run OCR first and record that you did."
        )

    return pages


def extract_pages_from(path: Path) -> list[str]:
    return extract_pages(Path(path).read_bytes())
