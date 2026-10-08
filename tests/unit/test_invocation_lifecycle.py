"""INVARIANT: a revoked invocation is history, never the live stage.

The invoked stage is the fact that decides whether ANY obligation applies. It can also be
revoked by a later order. Those two facts only coexist safely if the model refuses to confuse
them -- otherwise January's Stage III keeps enforcing in October, which is the single most
plausible way this corpus could quietly lie.

So these tests pin the distinction:

  * an ACTIVE invocation is what `invoked_stage()` returns;
  * a REVOKED invocation is available from `invocation_history()` and nowhere else;
  * a revocation with no citation is refused (an assertion cannot enter the corpus);
  * a quote that does not NAME the stage it invokes is refused, so the stage number cannot be
    edited while leaving the evidence untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_cli.corpus import EntryRejected, invoke_stage
from aadesh_core.domain import InvocationLifecycle
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.verification import verify_corpus
from tests.support.corpus_builder import CorpusBuilder

DUST_SENTENCE = "All dust generating construction activities shall remain suspended."
PAGE_TEXT = "5. The Sub-Committee on GRAP hereby invokes Stage III of the GRAP in the entire NCR.\n"
STAGE_QUOTE = "The Sub-Committee on GRAP hereby invokes Stage III of the GRAP"
REVOKE_TEXT = (
    "4. The Sub-Committee hereby revokes its order invoking Stage III, with immediate effect.\n"
)
REVOKE_QUOTE = "The Sub-Committee hereby revokes its order invoking Stage III"
INVOKED_AT = "2026-01-16T00:00:00+05:30"
REVOKED_AT = "2026-01-22T00:00:00+05:30"


def invocation(**over) -> dict:
    payload = {
        "stage": 3,
        "source_doc": "order-a",
        "page": 2,
        "quote": STAGE_QUOTE,
        "invoked_at": INVOKED_AT,
    }
    payload.update(over)
    return payload


def revocation() -> dict:
    return {
        "source_doc": "order-a",
        "page": 3,
        "quote": REVOKE_QUOTE,
        "revoked_at": REVOKED_AT,
    }


def corpus_with(tmp_path: Path, invoked: dict, *, stage_quote_page: str = PAGE_TEXT) -> Path:
    root = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document(doc_id="order-a")
        .with_page(doc_id="order-a", page=2, text=stage_quote_page)
        .with_page(doc_id="order-a", page=3, text=REVOKE_TEXT)
        .build()
    )
    (root / "invoked_stage.json").write_text(
        json.dumps({"invoked": invoked}, indent=2), encoding="utf-8"
    )
    return root


# --- active vs revoked ------------------------------------------------------


def test_a_cited_active_invocation_is_current(tmp_path):
    root = corpus_with(tmp_path, invocation())
    stage = LocalFileCorpus(root).invoked_stage()
    assert stage is not None
    assert stage.is_current is True
    assert stage.lifecycle is InvocationLifecycle.ACTIVE
    assert "Current:" in stage.describe()


def test_a_revoked_invocation_is_history_and_never_current(tmp_path):
    root = corpus_with(tmp_path, invocation(lifecycle="revoked", revocation=revocation()))
    assert not verify_corpus(root).has_failures

    corpus = LocalFileCorpus(root)
    # The load-bearing assertion: nothing is CURRENTLY in force.
    assert corpus.invoked_stage() is None

    (historical,) = corpus.invocation_history()
    assert historical.lifecycle is InvocationLifecycle.REVOKED
    assert historical.is_current is False
    assert historical.revoked_at is not None
    assert historical.revocation_citation is not None
    assert "Historical replay" in historical.describe()
    assert "not currently in force" in historical.describe()


def test_a_revocation_without_its_citation_is_refused(tmp_path):
    """'It was revoked' is a legal fact and cannot be taken on trust."""
    root = corpus_with(tmp_path, invocation(lifecycle="revoked"))
    with pytest.raises(CorpusIntegrityError, match="revocation"):
        LocalFileCorpus(root).invoked_stage()


def test_a_revocation_whose_quote_is_absent_from_its_page_is_refused(tmp_path):
    bad = revocation() | {"quote": "the stage lapsed because the air improved"}
    root = corpus_with(tmp_path, invocation(lifecycle="revoked", revocation=bad))
    assert verify_corpus(root).has_failures
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(root).invocation_history()


# --- the quote must name the stage it invokes ------------------------------


def test_a_stage_whose_quote_does_not_name_it_is_refused(tmp_path):
    root = corpus_with(tmp_path, invocation(quote=DUST_SENTENCE, stage=4))

    report = verify_corpus(root)
    assert report.has_failures
    assert any("does not name stage" in c.detail for c in report.citations_failed)
    with pytest.raises(CorpusIntegrityError, match="re-proved"):
        LocalFileCorpus(root).invoked_stage()


# --- the CLI cannot write an unsupported lifecycle -------------------------


def test_invoke_stage_refuses_revocation_without_evidence(tmp_path):
    root = corpus_with(tmp_path, invocation())  # any valid corpus is enough
    with pytest.raises(EntryRejected, match="revocation"):
        invoke_stage(
            corpus_root=root,
            stage=3,
            source_doc="order-a",
            page=2,
            quote=STAGE_QUOTE,
            lifecycle="revoked",
        )


def test_invoke_stage_records_a_revoked_record_the_loader_treats_as_history(tmp_path):
    root = corpus_with(tmp_path, invocation())
    (root / "invoked_stage.json").unlink()

    invoke_stage(
        corpus_root=root,
        stage=3,
        source_doc="order-a",
        page=2,
        quote=STAGE_QUOTE,
        invoked_at=INVOKED_AT,
        lifecycle="revoked",
        revocation=revocation(),
    )

    assert not verify_corpus(root).has_failures
    corpus = LocalFileCorpus(root)
    assert corpus.invoked_stage() is None
    (historical,) = corpus.invocation_history()
    assert historical.lifecycle is InvocationLifecycle.REVOKED
