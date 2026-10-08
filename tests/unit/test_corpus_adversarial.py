"""ADVERSARIAL PROVENANCE: prove the gate CATCHES a lying corpus, not just passes one.

`make verify` exiting 0 on the shipped corpus proves the happy path. It does not prove the
gate works, for the same reason a hash check that has never failed proves only that you did
not delete your files.

So every test below takes a SCRATCH COPY of the real, committed CAQM corpus, makes exactly
one hostile edit, and asserts that verification (or ingestion) refuses it. The scratch copy
means the real corpus is never touched, and the edits are the seven failure modes this
project's whole claim depends on catching:

  1. a flipped source byte           -> citation must fail
  2. a changed quoted sentence        -> citation must fail
  3. a changed cited page number      -> citation must fail
  4. a non-official mirror URL         -> ingestion AND verification must fail
  5. a changed invoked stage, same quote -> verification must fail (the quote must name it)
  6. a deleted source PDF, kept text   -> verification must fail
  7. a quote replaced by a paraphrase  -> citation must fail
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.sources import is_official_source_url
from aadesh_core.verification import verify_corpus

SCHEDULE_DOC = "caqm-grap-schedule-2026-09-29"
SCHEDULE_PDF = f"sources/{SCHEDULE_DOC}.pdf"
OBLIGATIONS = "obligations/construction_site.json"
INVOKED_STAGE = "invoked_stage.json"


@pytest.fixture
def corpus(tmp_path: Path, shipped_corpus: Path) -> Path:
    """A private copy of the real corpus, safe to deface."""
    root = tmp_path / "corpus"
    shutil.copytree(shipped_corpus, root)
    return root


def _edit(root: Path, relative: str, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = root / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --- the baseline the scratch copies diverge from --------------------------


def test_the_unmodified_scratch_copy_verifies_clean(corpus: Path):
    report = verify_corpus(corpus)
    assert not report.has_failures
    assert report.documents_verified == 3
    assert report.citations_verified == 14
    assert LocalFileCorpus(corpus).invoked_stage() is None  # revoked, not current


# --- 1. a flipped source byte ----------------------------------------------


def test_a_changed_source_byte_fails_verification(corpus: Path):
    pdf = corpus / SCHEDULE_PDF
    data = bytearray(pdf.read_bytes())
    data[-1] ^= 0xFF
    pdf.write_bytes(bytes(data))

    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("hash mismatch" in d.detail for d in report.documents_failed)


# --- 2. a changed quoted sentence ------------------------------------------


def test_a_changed_quoted_sentence_fails_verification(corpus: Path):
    def mutate(payload: dict[str, Any]) -> None:
        payload["obligations"][0]["quote"] = "All construction and demolition work shall stop"

    _edit(corpus, OBLIGATIONS, mutate)
    report = verify_corpus(corpus)
    assert report.has_failures
    assert any(c.ok is False for c in report.citations)


# --- 3. a changed cited page number ----------------------------------------


def test_a_changed_cited_page_fails_verification(corpus: Path):
    def mutate(payload: dict[str, Any]) -> None:
        payload["obligations"][0]["page"] = 3  # exists, but does not hold this quote

    _edit(corpus, OBLIGATIONS, mutate)
    report = verify_corpus(corpus)
    assert report.has_failures


# --- 4. a non-official mirror URL ------------------------------------------


def test_a_mirror_url_in_the_manifest_fails_verification(corpus: Path):
    def mutate(payload: dict[str, Any]) -> None:
        payload["documents"][0]["source_url"] = "https://some-mirror.example/caqm-schedule.pdf"

    _edit(corpus, "sources/manifest.json", mutate)
    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("official" in d.detail for d in report.documents_failed)


def test_the_official_url_helper_rejects_mirrors_and_accepts_caqm():
    assert is_official_source_url("https://caqm.nic.in/x.pdf")
    assert is_official_source_url("https://www.caqm.nic.in/x.pdf")
    assert not is_official_source_url("https://some-mirror.example/x.pdf")
    # A lookalike host is not a subdomain: the match is on the host, not the string.
    assert not is_official_source_url("https://caqm.nic.in.evil.example/x.pdf")
    assert not is_official_source_url("")


# --- 5. a changed invoked stage, same quote --------------------------------


def test_changing_the_invoked_stage_without_its_quote_fails_verification(corpus: Path):
    def mutate(payload: dict[str, Any]) -> None:
        payload["invoked"]["stage"] = 4  # the quote still says Stage-III

    _edit(corpus, INVOKED_STAGE, mutate)
    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("does not name stage" in c.detail for c in report.citations_failed)

    # The loader refuses the same record verification rejected: the two must not disagree.
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(corpus).invocation_history()


# --- 6. a deleted source PDF, page text kept -------------------------------


def test_a_deleted_source_pdf_fails_verification_even_with_page_text(corpus: Path):
    (corpus / SCHEDULE_PDF).unlink()
    assert (corpus / "sources" / "pages" / SCHEDULE_DOC / "p11.txt").exists()

    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("file missing" in d.detail for d in report.documents_failed)


# --- 7. a quote replaced by a paraphrase -----------------------------------


def test_a_paraphrased_quote_fails_verification(corpus: Path):
    def mutate(payload: dict[str, Any]) -> None:
        payload["obligations"][0]["quote"] = "dust-generating construction must be suspended"

    _edit(corpus, OBLIGATIONS, mutate)
    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("not found" in c.detail for c in report.citations_failed)
