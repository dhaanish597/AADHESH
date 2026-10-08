"""INVARIANT: the loader is what connects verification to resolution.

The resolver refuses unsourced clauses, but that only protects anything if something
actually decides which clauses are sourced. That is this module's job, and getting it wrong
in the permissive direction would silently undo every other guarantee: a loader that marked
everything VERIFIED would leave the resolver's check doing nothing while still reporting
`fully_sourced=True`.

So the rule is: VERIFIED comes from a passing verification run, never from the file.
"""

from __future__ import annotations

import json

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain import InvocationLifecycle, SourceState
from aadesh_core.errors import CorpusIntegrityError
from tests.support.corpus_builder import CorpusBuilder

PAGE_TEXT = (
    "4. All dust generating construction and demolition activities shall remain "
    "suspended in the NCR until further orders.\n"
)
VERBATIM = "dust generating construction and demolition activities shall remain suspended"


def _corpus(tmp_path, quote=VERBATIM):
    return (
        CorpusBuilder(tmp_path / "corpus")
        .with_document()
        .with_page(text=PAGE_TEXT)
        .with_obligation(quote=quote)
        .build()
    )


def test_verified_quote_loads_as_verified(tmp_path):
    corpus = LocalFileCorpus(_corpus(tmp_path))
    (obligation,) = corpus.obligations()
    assert obligation.source_state is SourceState.VERIFIED


def test_paraphrased_quote_loads_as_unsourced_rather_than_being_dropped(tmp_path):
    """Loaded but excluded. Dropping it silently would hide an authoring error."""
    corpus = LocalFileCorpus(_corpus(tmp_path, quote="all dusty work must stop"))
    (obligation,) = corpus.obligations()
    assert obligation.source_state is SourceState.UNSOURCED


def test_source_state_in_the_file_is_ignored(tmp_path):
    """A corpus file cannot assert its own verification. Only the verifier can."""
    root = _corpus(tmp_path, quote="a paraphrase that will not verify")
    path = root / "obligations" / "construction_site.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["obligations"][0]["source_state"] = "verified"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError, match="source_state"):
        LocalFileCorpus(root).obligations()


def test_the_shipped_corpus_loads_fully_sourced(shipped_corpus):
    """Every encoded obligation and band re-proved against the official CAQM bytes."""
    corpus = LocalFileCorpus(shipped_corpus)
    obligations = corpus.obligations()
    bands = corpus.stage_bands()
    assert obligations and all(o.source_state is SourceState.VERIFIED for o in obligations)
    assert bands and all(b.source_state is SourceState.VERIFIED for b in bands)
    # No stage is CURRENTLY in force: the only invocation on record was revoked in January.
    assert corpus.invoked_stage() is None


def test_the_shipped_corpus_keeps_the_revoked_invocation_as_history(shipped_corpus):
    """The distinction the lifecycle exists for: history is available, but never live."""
    (invocation,) = LocalFileCorpus(shipped_corpus).invocation_history()
    assert invocation.stage == 3
    assert invocation.lifecycle is InvocationLifecycle.REVOKED
    assert invocation.is_current is False
    assert invocation.revoked_at is not None
    assert invocation.revocation_citation is not None
    assert "Historical replay" in invocation.describe()
    assert "not currently in force" in invocation.describe()


def test_a_tampered_source_unsources_every_entry_that_cites_it(tmp_path):
    """The page text is intact; the document it was extracted FROM is not. Still unsourced.

    Extracted text is a cache of what a document said. If the document's bytes no longer
    hash to the manifest, that cache is not evidence about anything -- and a loader that
    kept calling the entry VERIFIED would let a tampered source keep enforcing.
    """
    root = _corpus(tmp_path)
    (root / "sources" / "test-order.pdf").write_bytes(b"%PDF-1.4 something else entirely")

    (obligation,) = LocalFileCorpus(root).obligations()
    assert obligation.source_state is SourceState.UNSOURCED


def test_schema_violation_raises_rather_than_degrading(tmp_path):
    root = _corpus(tmp_path)
    path = root / "obligations" / "construction_site.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["obligations"][0]["operator"] = "approximately"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError, match="operator"):
        LocalFileCorpus(root).obligations()


def test_unknown_entity_type_is_rejected_by_schema(tmp_path):
    """Scope is one entity type, enforced at the schema boundary."""
    root = _corpus(tmp_path)
    path = root / "obligations" / "construction_site.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["obligations"][0]["entity_types"] = ["school"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(root).obligations()


def test_verification_report_is_exposed_for_reporting(tmp_path):
    corpus = LocalFileCorpus(_corpus(tmp_path))
    report = corpus.verification_report()
    assert report.citations_verified == 1
    assert report.documents_verified == 1
