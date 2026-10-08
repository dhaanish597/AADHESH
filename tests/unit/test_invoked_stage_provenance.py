"""INVARIANT: the invoked stage is cited, verified, and refused when it cannot be re-proved.

The invoked stage is the single most load-bearing legal fact in the system. It is what makes
an obligation applicable at all. Everything else in the corpus gates on verification, but
`invoked_stage.json` used to sit outside that gate: a stage could be recorded with no
citation, and the loader would hand it straight to the resolver.

That asymmetry is exactly what an attacker, or a tired author at 3am, would exploit. So the
invoked stage is now a citation like any other: it carries `source_doc`, `page` and `quote`,
`make verify` re-proves it, and the loader refuses it when the proof fails rather than
degrading to "nothing applies" -- which would silently drop every obligation in the corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_cli.verify import VerifyExit, run_verify
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.verification import verify_corpus
from tests.support.corpus_builder import CorpusBuilder

PAGE_TEXT = (
    "4. All dust generating construction and demolition activities shall remain "
    "suspended in the NCR until further orders.\n"
    "5. The Sub-Committee on GRAP hereby invokes Stage III of the GRAP in the entire NCR.\n"
)
VERBATIM = "dust generating construction and demolition activities shall remain suspended"
#: The invocation quote must NAME the stage it invokes, so it is a different sentence from
#: an obligation's quote. Verification refuses a stage number whose sentence does not state it.
STAGE_QUOTE = "The Sub-Committee on GRAP hereby invokes Stage III of the GRAP"
INVOKED_AT = "2026-10-08T06:00:00+05:30"


def corpus_with(tmp_path: Path, invoked: dict | None, *, tamper: bool = False) -> Path:
    root = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document(doc_id="order-a")
        .with_page(doc_id="order-a", page=4, text=PAGE_TEXT)
        .build()
    )
    if tamper:
        # Rewrite the stored bytes so they no longer hash to the manifest.
        (root / "sources" / "order-a.pdf").write_bytes(b"%PDF-1.4 tampered")
    (root / "invoked_stage.json").write_text(json.dumps({"invoked": invoked}), encoding="utf-8")
    return root


def invocation(**overrides) -> dict:
    payload = {
        "stage": 3,
        "source_doc": "order-a",
        "page": 4,
        "quote": STAGE_QUOTE,
        "invoked_at": INVOKED_AT,
    }
    payload.update(overrides)
    return payload


# --- the honest path ------------------------------------------------------


def test_a_cited_invocation_verifies_and_loads(tmp_path):
    root = corpus_with(tmp_path, invocation())
    report = verify_corpus(root)
    assert not report.has_failures
    assert report.citations_verified == 1

    stage = LocalFileCorpus(root).invoked_stage()
    assert stage is not None
    assert stage.stage == 3
    assert stage.order_doc_id == "order-a"
    assert (
        stage.order_sha256
        == json.loads((root / "sources" / "manifest.json").read_text(encoding="utf-8"))[
            "documents"
        ][0]["sha256"]
    )


def test_a_null_invocation_is_not_a_failure(tmp_path):
    """The shape this repo ships. Nothing is invoked, so nothing is claimed, so nothing fails."""
    root = corpus_with(tmp_path, None)
    assert not verify_corpus(root).has_failures
    assert LocalFileCorpus(root).invoked_stage() is None


# --- the failure this file exists for -------------------------------------


def test_an_invocation_with_no_citation_fails_verification(tmp_path):
    root = corpus_with(
        tmp_path,
        {"stage": 3, "source_doc": "order-a", "invoked_at": INVOKED_AT},
    )
    report = verify_corpus(root)
    assert report.has_failures
    assert any("invoked_stage.json" in error for error in report.errors)


def test_and_make_verify_exits_non_zero_for_it(tmp_path, capsys):
    root = corpus_with(
        tmp_path,
        {"stage": 3, "source_doc": "order-a", "invoked_at": INVOKED_AT},
    )
    assert run_verify(corpus_root=root, tamper=False, with_index=False) == VerifyExit.FAILED


def test_the_loader_refuses_an_unproved_invocation(tmp_path):
    """Not degraded to None. Dropping it would silently drop every obligation with it.

    Every field is well formed here, and the citation is complete. The ONLY thing wrong is
    that the quoted sentence is not on the page it names -- so this exercises the proof gate
    itself rather than the shape checks that run before it.
    """
    root = corpus_with(tmp_path, invocation(quote="the Commission invokes Stage III"))
    with pytest.raises(CorpusIntegrityError, match="re-proved"):
        LocalFileCorpus(root).invoked_stage()


def test_an_invocation_quoting_a_paraphrase_fails(tmp_path):
    root = corpus_with(tmp_path, invocation(quote="the Commission invokes Stage III"))
    assert verify_corpus(root).has_failures
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(root).invoked_stage()


def test_an_invocation_whose_order_bytes_were_tampered_with_is_refused(tmp_path):
    """The quote is intact; the document it is quoted from is not. Still refused."""
    root = corpus_with(tmp_path, invocation(), tamper=True)
    report = verify_corpus(root)
    assert report.documents_failed
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(root).invoked_stage()


def test_an_invocation_citing_an_unhashed_order_is_refused(tmp_path):
    root = corpus_with(tmp_path, invocation(source_doc="some-other-order"))
    with pytest.raises(CorpusIntegrityError, match="some-other-order"):
        LocalFileCorpus(root).invoked_stage()


# --- shape: one key name for every citation -------------------------------


def test_the_old_order_doc_id_key_is_refused_with_a_pointer_to_the_new_one(tmp_path):
    """A silent rename would leave the stage unverified while looking deliberate."""
    root = corpus_with(tmp_path, {"stage": 3, "invoked_at": INVOKED_AT})
    path = root / "invoked_stage.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["invoked"]["order_doc_id"] = "order-a"
    payload["invoked"]["page"] = 4
    payload["invoked"]["quote"] = STAGE_QUOTE
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError, match="source_doc"):
        LocalFileCorpus(root).invoked_stage()


@pytest.mark.parametrize(
    "broken, match",
    [
        ({"stage": 0}, "stage"),
        ({"page": 0}, "page"),
        ({"quote": ""}, "quote"),
        ({"invoked_at": "last Tuesday"}, "invoked_at"),
        ({"unexpected": True}, "unexpected"),
    ],
)
def test_a_malformed_invocation_stops_loudly(tmp_path, broken, match):
    root = corpus_with(tmp_path, invocation(**broken))
    with pytest.raises(CorpusIntegrityError, match=match):
        LocalFileCorpus(root).invoked_stage()
