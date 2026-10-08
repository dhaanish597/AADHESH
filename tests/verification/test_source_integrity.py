"""SOURCE INTEGRITY — the corpus is the only door, and every door has a hash on it.

The claim under test: a citation in this system is not a string that says "source_doc page 4".
It is a pointer into bytes that were hashed, whose extracted page text was hashed again, and
whose quoted sentence is re-found verbatim on that page. Break any link and the entry stops
being verifiable -- and, more importantly, stops being actionable.

Every check here runs against the REAL shipped corpus (`corpus/`), not a fixture, because the
thing being verified is the integrity of the bytes we actually ship.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_cli.verify import VerifyExit, run_verify
from aadesh_core.citations import labelled_citations, normalise, page_text_sha256
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.verification import verify_corpus
from tests.support.corpus_builder import CorpusBuilder
from tests.verification.harness import build_corpus

MANIFEST = "sources/manifest.json"


def _copy_corpus(source: Path, destination: Path) -> Path:
    """A private, writable copy. Nothing here ever touches `corpus/` itself."""
    shutil.copytree(source, destination)
    return destination


def _documents(corpus: Path) -> list[dict]:
    return json.loads((corpus / MANIFEST).read_text(encoding="utf-8"))["documents"]


# --- the hashes are real -----------------------------------------------------


def test_every_authoritative_source_matches_its_recorded_sha256(shipped_corpus: Path) -> None:
    documents = _documents(shipped_corpus)
    assert documents, "the shipped corpus must carry at least one authoritative source"
    for document in documents:
        body = (shipped_corpus / document["local_path"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == document["sha256"], document["doc_id"]
        assert len(body) == document["byte_size"], document["doc_id"]


def test_every_extracted_page_matches_its_recorded_sha256(shipped_corpus: Path) -> None:
    """The page cache is the thing a quote is checked against, so it needs its own hash.

    Without this, editing the extracted text would leave the PDF hash intact and quietly
    re-point every quote at new bytes.
    """
    for document in _documents(shipped_corpus):
        pages_dir = shipped_corpus / document["pages_dir"]
        recorded = document.get("page_sha256") or {}
        assert recorded, f"{document['doc_id']} records no page hashes"
        for page, expected in recorded.items():
            text = (pages_dir / f"p{page}.txt").read_text(encoding="utf-8")
            assert page_text_sha256(text) == expected, f"{document['doc_id']} p{page}"


# --- the citations land where they say they land -----------------------------


def test_every_citation_in_the_shipped_corpus_re_proves(shipped_corpus: Path) -> None:
    report = verify_corpus(shipped_corpus)
    assert not report.errors, report.errors
    assert not report.documents_failed, [d.detail for d in report.documents_failed]
    assert not report.citations_failed, [c.detail for c in report.citations_failed]
    assert report.citations_verified > 0
    assert report.is_empty is False


def test_a_verified_citation_quote_is_physically_present_on_the_page_it_names(
    shipped_corpus: Path,
) -> None:
    """Independent re-check of the verifier's boolean: for every citation written anywhere in
    the corpus files, go to the page text and find the quoted sentence ourselves.

    This deliberately re-derives the check with different code (`labelled_citations` +
    `normalise`) rather than calling the verifier again, so a bug in the verifier cannot make
    this test agree with it.
    """
    documents = {d["doc_id"]: d for d in _documents(shipped_corpus)}
    checked = 0
    for path in sorted(shipped_corpus.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for _, citation in labelled_citations(payload):
            document = documents.get(citation["source_doc"])
            assert document is not None, f"{path.name}: cites unknown doc {citation['source_doc']}"
            page = (shipped_corpus / document["pages_dir"] / f"p{citation['page']}.txt").read_text(
                encoding="utf-8"
            )
            assert normalise(citation["quote"]) in normalise(page), (
                f"{path.name}: quote is not on {citation['source_doc']} p{citation['page']}"
            )
            checked += 1
    assert checked > 0, "no citations found in the shipped corpus"


# --- tampering is caught -----------------------------------------------------


def test_a_flipped_source_byte_fails_verification(shipped_corpus: Path, tmp_path: Path) -> None:
    corpus = _copy_corpus(shipped_corpus, tmp_path / "corpus")
    document = _documents(corpus)[0]
    pdf = corpus / document["local_path"]
    body = bytearray(pdf.read_bytes())
    body[0] ^= 0x01
    pdf.write_bytes(bytes(body))

    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("hash mismatch" in check.detail for check in report.documents_failed)


def test_a_changed_page_byte_fails_verification(shipped_corpus: Path, tmp_path: Path) -> None:
    corpus = _copy_corpus(shipped_corpus, tmp_path / "corpus")
    document = _documents(corpus)[0]
    page = corpus / document["pages_dir"] / "p1.txt"
    page.write_text(page.read_text(encoding="utf-8") + "\nan appended sentence\n", "utf-8")

    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("page" in check.detail for check in report.citations_failed)


def test_a_tampered_source_cannot_produce_a_verified_corpus(
    shipped_corpus: Path, tmp_path: Path
) -> None:
    """The load path, not just the report: a tampered document must not reach the resolver.

    This is the difference between "we can tell you it is broken" and "we will not act on it".
    """
    corpus = _copy_corpus(shipped_corpus, tmp_path / "corpus")
    document = _documents(corpus)[0]
    pdf = corpus / document["local_path"]
    body = bytearray(pdf.read_bytes())
    body[-1] ^= 0x01
    pdf.write_bytes(bytes(body))

    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(corpus).snapshot()


def test_a_missing_cited_page_cannot_produce_a_verified_corpus(tmp_path: Path) -> None:
    """A citation whose page is absent is not a citation. `snapshot()` refuses rather than
    degrading the entry to unsourced-and-quietly-ignored."""
    corpus = build_corpus(tmp_path / "corpus")
    page = corpus / "sources" / "pages" / "test-grap-order" / "p4.txt"
    page.unlink()

    report = verify_corpus(corpus)
    assert report.has_failures
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(corpus).snapshot()


def test_a_paraphrased_quote_is_not_proved_verbatim(tmp_path: Path) -> None:
    """Proof, not fuzzy matching: a reworded sentence that means the same thing fails."""
    corpus = build_corpus(tmp_path / "corpus")
    entry = json.loads((corpus / "obligations" / "construction_site.json").read_text("utf-8"))
    original = entry["obligations"][0]["quote"]
    entry["obligations"][0]["quote"] = original.replace("shall be suspended", "must stop")
    (corpus / "obligations" / "construction_site.json").write_text(
        json.dumps(entry, indent=2), encoding="utf-8"
    )

    report = verify_corpus(corpus)
    assert report.has_failures
    assert any("quote not found" in check.detail for check in report.citations_failed)


def test_an_uncited_entry_cannot_enter_the_corpus(tmp_path: Path) -> None:
    """An obligation with no evidence key at all is a corpus-integrity failure, not a rule."""
    corpus = build_corpus(tmp_path / "corpus")
    entry = json.loads((corpus / "obligations" / "construction_site.json").read_text("utf-8"))
    del entry["obligations"][0]["evidence"]
    (corpus / "obligations" / "construction_site.json").write_text(
        json.dumps(entry, indent=2), encoding="utf-8"
    )

    report = verify_corpus(corpus)
    assert report.has_failures


# --- the two CLI gates -------------------------------------------------------


def test_verify_exits_zero_on_the_shipped_corpus(shipped_corpus: Path) -> None:
    assert run_verify(corpus_root=shipped_corpus) is VerifyExit.OK


def test_verify_tamper_exits_non_zero_and_leaves_the_real_corpus_untouched(
    shipped_corpus: Path, tmp_path: Path
) -> None:
    """`make verify-tamper` is a check that MUST fail. If it ever exits zero, the detector is
    broken and the whole corpus claim is decorative. Run it on a copy so the shipped bytes are
    provably byte-identical afterwards."""
    before = {p: p.read_bytes() for p in shipped_corpus.rglob("*") if p.is_file()}
    corpus = _copy_corpus(shipped_corpus, tmp_path / "corpus")

    exit_code = run_verify(corpus_root=corpus, tamper=True)

    assert exit_code is not VerifyExit.OK
    assert int(exit_code) != 0
    after = {p: p.read_bytes() for p in shipped_corpus.rglob("*") if p.is_file()}
    assert before == after, "the tamper check must never modify the authoritative corpus"


def test_a_corpus_with_nothing_to_prove_is_not_reported_as_verified(tmp_path: Path) -> None:
    """Zero verified citations is `CORPUS_NOT_READY`, never `OK`. An empty corpus must not be
    able to masquerade as a verified one."""
    empty = CorpusBuilder(tmp_path / "corpus").build()
    assert run_verify(corpus_root=empty) is VerifyExit.CORPUS_NOT_READY


def test_a_corpus_with_no_manifest_at_all_is_never_ok(tmp_path: Path) -> None:
    """A directory that is not a corpus is a failure, not a readiness state. This is the other
    half of the same guarantee: `OK` means "every citation re-proved", so it must be
    unreachable when there is no manifest to prove anything against."""
    empty = tmp_path / "corpus"
    empty.mkdir()
    assert run_verify(corpus_root=empty) is not VerifyExit.OK
