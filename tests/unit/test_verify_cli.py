"""INVARIANTS for the verification gate.

Two things must be true for `make verify` to mean anything:

  * **It fails when there is nothing to prove.** A corpus with zero verified citations is
    not a passing state; it is an unfinished one. Exiting 0 there would make the gate a
    decoration, and the Day 1 state of this repo is exactly that case.
  * **It catches tampering.** A hash check that has never failed proves only that you did
    not delete your files. `--tamper` flips a byte in a scratch copy and asserts detection.

Exit codes are distinct so CI and a human can tell "not ready yet" from "something is wrong".
"""

from __future__ import annotations

import pytest

from aadesh_cli.verify import VerifyExit, run_verify
from tests.support.corpus_builder import CorpusBuilder

PAGE_TEXT = (
    "4. All dust generating construction and demolition activities shall remain "
    "suspended in the NCR until further orders.\n"
)
VERBATIM = "dust generating construction and demolition activities shall remain suspended"


@pytest.fixture
def empty_corpus(tmp_path):
    return CorpusBuilder(tmp_path / "corpus").build()


@pytest.fixture
def good_corpus(tmp_path):
    return (
        CorpusBuilder(tmp_path / "corpus")
        .with_document()
        .with_page(text=PAGE_TEXT)
        .with_obligation(quote=VERBATIM)
        .build()
    )


def _run(corpus, **kw):
    return run_verify(corpus_root=corpus, stream=kw.pop("stream", None), **kw)


# --- the Day 1 state -------------------------------------------------------


def test_empty_corpus_exits_corpus_not_ready(empty_corpus, capsys):
    code = _run(empty_corpus)
    assert code == VerifyExit.CORPUS_NOT_READY
    assert code != 0


def test_empty_corpus_failure_is_explicit_and_actionable(empty_corpus, capsys):
    """Not a generic assertion error. Someone reading this must know what to do next."""
    _run(empty_corpus)
    out = capsys.readouterr().out
    assert "zero verified citations" in out.lower()
    assert "caqm" in out.lower()
    assert "sha256" in out.lower() or "sha-256" in out.lower()
    assert "drop that measure" in out.lower()
    assert "CORPUS_NOT_READY" in out


def test_the_shipped_repo_corpus_is_in_the_not_ready_state(repo_root, capsys):
    """Asserts the committed corpus really is empty, so nobody fabricated data to go green."""
    assert _run(repo_root / "corpus") == VerifyExit.CORPUS_NOT_READY


# --- the passing state -----------------------------------------------------


def test_fully_verified_corpus_exits_ok(good_corpus, capsys):
    assert _run(good_corpus) == VerifyExit.OK
    assert "VERIFIED" in capsys.readouterr().out


def test_report_counts_documents_and_citations(good_corpus, capsys):
    _run(good_corpus)
    out = capsys.readouterr().out
    assert "1" in out
    assert "citations" in out.lower()


# --- the failing states ----------------------------------------------------


def test_paraphrased_quote_fails_verification(tmp_path, capsys):
    """The mechanism that stops remembered law creeping in under deadline pressure."""
    corpus = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document()
        .with_page(text=PAGE_TEXT)
        .with_obligation(quote="all dusty building work must stop")
        .build()
    )
    assert _run(corpus) == VerifyExit.FAILED
    assert "not found" in capsys.readouterr().out.lower()


def test_hash_mismatch_fails_verification(tmp_path, capsys):
    corpus = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document(sha256="0" * 64)
        .with_page(text=PAGE_TEXT)
        .with_obligation(quote=VERBATIM)
        .build()
    )
    assert _run(corpus) == VerifyExit.FAILED
    assert "hash" in capsys.readouterr().out.lower()


def test_citation_to_a_missing_page_fails(tmp_path, capsys):
    corpus = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document()
        .with_page(page=4, text=PAGE_TEXT)
        .with_obligation(page=9, quote=VERBATIM)
        .build()
    )
    assert _run(corpus) == VerifyExit.FAILED


def test_citation_to_an_unknown_document_fails(tmp_path, capsys):
    corpus = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document(doc_id="order-a")
        .with_page(doc_id="order-a", text=PAGE_TEXT)
        .with_obligation(doc_id="order-b", quote=VERBATIM)
        .build()
    )
    assert _run(corpus) == VerifyExit.FAILED
    assert "unknown" in capsys.readouterr().out.lower()


# --- tamper detection ------------------------------------------------------


def test_tamper_detects_a_flipped_byte_and_exits_non_zero(good_corpus, capsys):
    code = _run(good_corpus, tamper=True)
    assert code != 0
    assert code == VerifyExit.FAILED
    out = capsys.readouterr().out
    assert "expected" in out.lower()
    assert "tamper" in out.lower()


def test_tamper_does_not_modify_the_real_corpus(good_corpus):
    before = (good_corpus / "sources" / "test-order.pdf").read_bytes()
    _run(good_corpus, tamper=True)
    assert (good_corpus / "sources" / "test-order.pdf").read_bytes() == before
    assert _run(good_corpus) == VerifyExit.OK


def test_tamper_on_an_empty_corpus_reports_it_cannot_prove_anything(empty_corpus, capsys):
    """Honest: with no source documents there is nothing to tamper with, so the check
    proves nothing and must not pretend otherwise."""
    code = _run(empty_corpus, tamper=True)
    assert code == VerifyExit.TAMPER_UNPROVABLE
    assert code != 0
    assert "cannot prove" in capsys.readouterr().out.lower()


def test_exit_codes_are_distinct():
    values = [
        VerifyExit.OK,
        VerifyExit.FAILED,
        VerifyExit.CORPUS_NOT_READY,
        VerifyExit.TAMPER_UNPROVABLE,
        VerifyExit.TAMPER_NOT_DETECTED,
    ]
    assert len(set(values)) == len(values)
    assert VerifyExit.OK == 0
    assert all(v != 0 for v in values[1:])
