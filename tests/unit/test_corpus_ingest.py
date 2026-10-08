"""The ingestion mechanism: the ONLY sanctioned way bytes and clauses enter the corpus.

Two jobs, and both of them exist to make a lie impossible to commit by accident:

  * `ingest_document` -- take the bytes you actually downloaded, hash them, store them, and
    record where they came from. Nothing enters the manifest that is not byte-for-byte what
    was on disk at the moment it was hashed.
  * `add_entry` -- accept an obligation or entitlement ONLY when its `quote` is found
    verbatim on the page it cites. The check uses the SAME normalisation the verifier uses,
    so the writer cannot accept something `make verify` will reject. If those two ever
    disagree, this whole project's central claim is theatre.

The tests below deliberately include a paraphrase, a quote that lives on the wrong page, an
invented rupee figure, and a corpus entry declaring itself verified. Each must be refused.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aadesh_cli.corpus import (
    CorpusExit,
    EntryRejected,
    IngestError,
    QuoteNotFound,
    add_entry,
    ingest_document,
    invoke_stage,
    main,
)
from aadesh_core.verification import verify_corpus
from tests.support.corpus_builder import CorpusBuilder
from tests.support.pdf_builder import make_pdf

PAGE_ONE = "dust generating construction activities shall remain suspended"
PAGE_TWO = "the Authority's direction issued under section 5 shall be complied with"
URL = "https://caqm.nic.in/orders/example-order.pdf"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_of(corpus: Path) -> list[dict]:
    """Tolerant on purpose: a refused ingest should leave no manifest behind at all."""
    path = corpus / "sources" / "manifest.json"
    return read_json(path)["documents"] if path.exists() else []


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "downloaded.pdf"
    path.write_bytes(make_pdf([PAGE_ONE, PAGE_TWO]))
    return path


class TestIngestDocument:
    def test_stores_the_exact_bytes_that_were_on_disk(self, tmp_path, pdf):
        corpus = tmp_path / "corpus"
        ingest_document(
            corpus_root=corpus,
            pdf_path=pdf,
            doc_id="caqm-test-order",
            source_url=URL,
        )
        assert (corpus / "sources" / "caqm-test-order.pdf").read_bytes() == pdf.read_bytes()

    def test_records_the_hash_of_those_bytes(self, tmp_path, pdf):
        corpus = tmp_path / "corpus"
        result = ingest_document(
            corpus_root=corpus, pdf_path=pdf, doc_id="caqm-test-order", source_url=URL
        )
        assert result.sha256 == hashlib.sha256(pdf.read_bytes()).hexdigest()
        assert result.byte_size == len(pdf.read_bytes())
        assert manifest_of(corpus)[0]["sha256"] == result.sha256

    def test_what_it_ingested_passes_verification(self, tmp_path, pdf):
        """Writer and verifier must agree. If they don't, nothing downstream means anything."""
        corpus = tmp_path / "corpus"
        ingest_document(corpus_root=corpus, pdf_path=pdf, doc_id="caqm-test-order", source_url=URL)
        report = verify_corpus(corpus)
        assert not report.has_failures
        assert report.documents_verified == 1

    def test_extracts_one_text_file_per_page_indexed_from_one(self, tmp_path, pdf):
        corpus = tmp_path / "corpus"
        result = ingest_document(
            corpus_root=corpus, pdf_path=pdf, doc_id="caqm-test-order", source_url=URL
        )
        pages = corpus / "sources" / "pages" / "caqm-test-order"
        assert result.page_count == 2
        assert sorted(p.name for p in pages.iterdir()) == ["p1.txt", "p2.txt"]
        assert PAGE_ONE.split()[0] in (pages / "p1.txt").read_text(encoding="utf-8")
        assert PAGE_TWO.split()[0] in (pages / "p2.txt").read_text(encoding="utf-8")

    def test_records_where_it_came_from_and_when(self, tmp_path, pdf):
        corpus = tmp_path / "corpus"
        ingest_document(
            corpus_root=corpus,
            pdf_path=pdf,
            doc_id="caqm-test-order",
            source_url=URL,
            title="Example order",
            publisher="CAQM",
            retrieved_at="2026-10-08T09:00:00+00:00",
        )
        doc = manifest_of(corpus)[0]
        assert doc["source_url"] == URL
        assert doc["retrieved_at"] == "2026-10-08T09:00:00+00:00"
        assert doc["title"] == "Example order"
        assert doc["publisher"] == "CAQM"

    def test_appends_without_clobbering_documents_already_in_the_manifest(self, tmp_path):
        corpus = tmp_path / "corpus"
        first = tmp_path / "first.pdf"
        first.write_bytes(make_pdf(["first order text"]))
        second = tmp_path / "second.pdf"
        second.write_bytes(make_pdf(["second order text"]))

        ingest_document(corpus_root=corpus, pdf_path=first, doc_id="order-a", source_url=URL)
        ingest_document(corpus_root=corpus, pdf_path=second, doc_id="order-b", source_url=URL)

        assert [d["doc_id"] for d in manifest_of(corpus)] == ["order-a", "order-b"]
        assert first.read_bytes() == (corpus / "sources" / "order-a.pdf").read_bytes()

    def test_refuses_a_doc_id_that_is_already_present(self, tmp_path, pdf):
        """Re-ingesting would silently orphan every citation that points at the old bytes."""
        corpus = tmp_path / "corpus"
        ingest_document(corpus_root=corpus, pdf_path=pdf, doc_id="order-a", source_url=URL)
        with pytest.raises(IngestError, match="order-a"):
            ingest_document(corpus_root=corpus, pdf_path=pdf, doc_id="order-a", source_url=URL)
        assert len(manifest_of(corpus)) == 1

    def test_refuses_bytes_that_are_not_a_pdf(self, tmp_path):
        corpus = tmp_path / "corpus"
        not_a_pdf = tmp_path / "notes.txt"
        not_a_pdf.write_bytes(b"someone's summary of the order. not the order. noqa: e501")
        with pytest.raises(IngestError, match="PDF"):
            ingest_document(
                corpus_root=corpus, pdf_path=not_a_pdf, doc_id="order-a", source_url=URL
            )

    def test_refuses_a_pdf_with_no_extractable_text(self, tmp_path):
        """A scan with no text layer cannot be cited from, so accepting it would be a trap."""
        corpus = tmp_path / "corpus"
        blank = tmp_path / "blank.pdf"
        blank.write_bytes(make_pdf(["   "]))
        with pytest.raises(IngestError):
            ingest_document(corpus_root=corpus, pdf_path=blank, doc_id="order-a", source_url=URL)

    def test_a_refused_ingest_leaves_nothing_behind(self, tmp_path):
        corpus = tmp_path / "corpus"
        blank = tmp_path / "blank.pdf"
        blank.write_bytes(make_pdf(["   "]))
        with pytest.raises(IngestError):
            ingest_document(corpus_root=corpus, pdf_path=blank, doc_id="order-a", source_url=URL)
        assert not (corpus / "sources" / "order-a.pdf").exists()
        assert manifest_of(corpus) == []

    @pytest.mark.parametrize("doc_id", ["../escape", "a/b", "", "Order A", ".", "a\\b"])
    def test_refuses_a_doc_id_that_is_not_a_safe_slug(self, tmp_path, pdf, doc_id):
        """doc_id becomes a filename. Traversal here would write outside the corpus."""
        corpus = tmp_path / "corpus"
        with pytest.raises(IngestError):
            ingest_document(corpus_root=corpus, pdf_path=pdf, doc_id=doc_id, source_url=URL)

    def test_refuses_a_missing_file_with_a_useful_message(self, tmp_path):
        corpus = tmp_path / "corpus"
        with pytest.raises(IngestError, match=r"no-such-file\.pdf"):
            ingest_document(
                corpus_root=corpus,
                pdf_path=tmp_path / "no-such-file.pdf",
                doc_id="order-a",
                source_url=URL,
            )


class TestAddEntry:
    @pytest.fixture
    def corpus(self, tmp_path) -> Path:
        return (
            CorpusBuilder(tmp_path / "corpus")
            .with_document(doc_id="order-a")
            .with_page(doc_id="order-a", page=4, text=f"Clause 7. {PAGE_ONE}. Also, {PAGE_TWO}.")
            .build()
        )

    def obligation(self, **overrides) -> dict:
        entry = {
            "obligation_id": "grap3-dust-01",
            "entity_types": ["construction_site"],
            "triggers_at_stage": 3,
            "label": "Suspend dust-generating activity",
            "field": "has_dust_generating_activity",
            "operator": "eq",
            "value": True,
            "source_doc": "order-a",
            "page": 4,
            "quote": PAGE_ONE,
            "consequence": {"issues_parchi": True},
        }
        entry.update(overrides)
        return entry

    def test_accepts_an_obligation_quoting_the_page_verbatim(self, corpus):
        add_entry(corpus_root=corpus, kind="obligation", entry=self.obligation())
        written = read_json(corpus / "obligations" / "construction_site.json")["obligations"]
        assert [o["obligation_id"] for o in written] == ["grap3-dust-01"]

    def test_and_the_verifier_then_reports_it_verified(self, corpus):
        """The point of the whole exercise: what the writer accepted, `make verify` proves."""
        add_entry(corpus_root=corpus, kind="obligation", entry=self.obligation())
        report = verify_corpus(corpus)
        assert not report.has_failures
        assert "grap3-dust-01" in report.verified_entry_ids

    def test_refuses_a_paraphrase(self, corpus):
        """The single most important refusal in this file."""
        paraphrased = self.obligation(quote="dust-generating work must stop")
        with pytest.raises(QuoteNotFound, match="page 4"):
            add_entry(corpus_root=corpus, kind="obligation", entry=paraphrased)
        assert read_json(corpus / "obligations" / "construction_site.json")["obligations"] == []

    def test_refuses_a_quote_that_lives_on_a_different_page_than_cited(self, corpus):
        (corpus / "sources" / "pages" / "order-a" / "p9.txt").write_text(PAGE_TWO, encoding="utf-8")
        with pytest.raises(QuoteNotFound, match="page 9"):
            add_entry(
                corpus_root=corpus,
                kind="obligation",
                entry=self.obligation(page=9, quote=PAGE_ONE),
            )

    def test_accepts_a_quote_differing_only_in_typography(self, corpus):
        """Same leniency the verifier allows, so the two cannot drift apart."""
        (corpus / "sources" / "pages" / "order-a" / "p5.txt").write_text(
            # The curly apostrophe and the run of spaces are the point: they are what
            # extraction introduces, and what the shared normalisation must fold away.
            "the Authority’s   direction\nissued under section 5",  # noqa: RUF001
            encoding="utf-8",
        )
        add_entry(
            corpus_root=corpus,
            kind="obligation",
            entry=self.obligation(page=5, quote="the Authority's direction issued under section 5"),
        )
        assert "grap3-dust-01" in verify_corpus(corpus).verified_entry_ids

    def test_refuses_an_entry_citing_a_document_not_in_the_manifest(self, corpus):
        with pytest.raises(EntryRejected, match="order-z"):
            add_entry(
                corpus_root=corpus, kind="obligation", entry=self.obligation(source_doc="order-z")
            )

    def test_refuses_an_entry_citing_a_page_with_no_extracted_text(self, corpus):
        with pytest.raises(EntryRejected, match="7"):
            add_entry(corpus_root=corpus, kind="obligation", entry=self.obligation(page=7))

    @pytest.mark.parametrize("key", ["source_state", "verified", "is_verified"])
    def test_refuses_an_entry_declaring_its_own_provenance(self, corpus, key):
        with pytest.raises(EntryRejected, match=key):
            add_entry(
                corpus_root=corpus, kind="obligation", entry=self.obligation(**{key: "VERIFIED"})
            )

    def test_refuses_an_entry_that_fails_its_schema(self, corpus):
        broken = self.obligation()
        del broken["consequence"]
        with pytest.raises(EntryRejected, match="consequence"):
            add_entry(corpus_root=corpus, kind="obligation", entry=broken)

    def test_refuses_a_duplicate_id(self, corpus):
        add_entry(corpus_root=corpus, kind="obligation", entry=self.obligation())
        with pytest.raises(EntryRejected, match="grap3-dust-01"):
            add_entry(corpus_root=corpus, kind="obligation", entry=self.obligation())

    def test_preserves_entries_already_present(self, corpus):
        add_entry(corpus_root=corpus, kind="obligation", entry=self.obligation())
        add_entry(
            corpus_root=corpus,
            kind="obligation",
            entry=self.obligation(obligation_id="grap3-dust-02", quote=PAGE_TWO),
        )
        written = read_json(corpus / "obligations" / "construction_site.json")["obligations"]
        assert [o["obligation_id"] for o in written] == ["grap3-dust-01", "grap3-dust-02"]

    def test_refuses_an_unknown_kind(self, corpus):
        with pytest.raises(EntryRejected, match="stage_band"):
            add_entry(corpus_root=corpus, kind="stage_band", entry=self.obligation())

    # -- entitlements: the rupee-fixture hazard -----------------------------

    def entitlement(self, **overrides) -> dict:
        entry = {
            "entitlement_id": "cess-displaced-worker-01",
            "label": "Displaced worker assistance",
            "source_doc": "order-a",
            "page": 4,
            "quote": PAGE_ONE,
            "amount": None,
            "readiness_requirements": [],
        }
        entry.update(overrides)
        return entry

    def test_accepts_an_entitlement_with_no_amount(self, corpus):
        """The honest default: report displaced worker-days, which are always provable."""
        add_entry(corpus_root=corpus, kind="entitlement", entry=self.entitlement())
        written = read_json(corpus / "entitlements" / "cess_fund.json")["entitlements"]
        assert written[0]["amount"] is None

    def test_accepts_an_amount_whose_own_quote_is_on_its_own_page(self, corpus):
        add_entry(
            corpus_root=corpus,
            kind="entitlement",
            entry=self.entitlement(
                amount={
                    "value_inr": 1000,
                    "basis": "per_worker_per_day",
                    "source_doc": "order-a",
                    "page": 4,
                    "quote": PAGE_TWO,
                }
            ),
        )
        assert "cess-displaced-worker-01" in verify_corpus(corpus).verified_entry_ids

    def test_refuses_an_amount_whose_quote_is_not_in_the_source(self, corpus):
        """This is the guard that stops a plausible rupee figure entering the corpus."""
        with pytest.raises(QuoteNotFound, match="amount"):
            add_entry(
                corpus_root=corpus,
                kind="entitlement",
                entry=self.entitlement(
                    amount={
                        "value_inr": 102000,
                        "basis": "per_worker_one_time",
                        "source_doc": "order-a",
                        "page": 4,
                        "quote": "a one-time assistance of Rs 1,02,000 per worker",
                    }
                ),
            )


class TestInvokeStage:
    """The invoked stage decides whether ANY obligation applies, so it is cited like the rest."""

    @pytest.fixture
    def corpus(self, tmp_path) -> Path:
        return (
            CorpusBuilder(tmp_path / "corpus")
            .with_document(doc_id="order-a")
            .with_page(doc_id="order-a", page=2, text=PAGE_ONE)
            .build()
        )

    def test_writes_a_cited_invocation_the_loader_then_accepts(self, corpus):
        from aadesh_adapters.corpus.local_file import LocalFileCorpus

        invoke_stage(
            corpus_root=corpus,
            stage=3,
            source_doc="order-a",
            page=2,
            quote=PAGE_ONE,
            invoked_at="2026-10-08T06:00:00+05:30",
        )
        assert not verify_corpus(corpus).has_failures
        stage = LocalFileCorpus(corpus).invoked_stage()
        assert stage is not None and stage.stage == 3

    def test_refuses_a_quote_that_is_not_on_the_cited_page(self, corpus):
        with pytest.raises(QuoteNotFound, match="invocation"):
            invoke_stage(
                corpus_root=corpus,
                stage=3,
                source_doc="order-a",
                page=2,
                quote="the Commission hereby invokes GRAP Stage III",
            )
        assert not (corpus / "invoked_stage.json").exists()

    def test_refuses_an_order_that_was_never_ingested(self, corpus):
        with pytest.raises(EntryRejected, match="order-z"):
            invoke_stage(
                corpus_root=corpus,
                stage=3,
                source_doc="order-z",
                page=2,
                quote=PAGE_ONE,
            )

    def test_refuses_a_page_with_no_extracted_text(self, corpus):
        with pytest.raises(EntryRejected, match="page 6"):
            invoke_stage(corpus_root=corpus, stage=3, source_doc="order-a", page=6, quote=PAGE_ONE)

    def test_refuses_a_stage_ordinal_below_one(self, corpus):
        with pytest.raises(EntryRejected, match="ordinal"):
            invoke_stage(corpus_root=corpus, stage=0, source_doc="order-a", page=2, quote=PAGE_ONE)

    def test_the_cli_exits_with_the_quote_code(self, corpus, capsys):
        code = main(
            [
                "invoke-stage",
                "--corpus",
                str(corpus),
                "--stage",
                "3",
                "--doc-id",
                "order-a",
                "--page",
                "2",
                "--quote",
                "the Commission hereby invokes GRAP Stage III",
            ]
        )
        assert code == CorpusExit.QUOTE_NOT_FOUND


class TestAddStageBand:
    """A band carries an AQI threshold. This is the one door such a number may come through."""

    @pytest.fixture
    def corpus(self, tmp_path) -> Path:
        return (
            CorpusBuilder(tmp_path / "corpus")
            .with_document(doc_id="order-a")
            .with_page(
                doc_id="order-a",
                page=2,
                text=f"Stage III shall apply when the AQI is between {PAGE_ONE}",
            )
            .build()
        )

    def band(self, **overrides) -> dict:
        entry = {
            "stage": 3,
            "pollutant": "AQI",
            "aqi_lower": 201,
            "aqi_upper": 300,
            "source_doc": "order-a",
            "page": 2,
            "quote": "Stage III shall apply when the AQI is between",
        }
        entry.update(overrides)
        return entry

    def test_accepts_a_band_quoting_the_threshold_it_states(self, corpus):
        add_entry(corpus_root=corpus, kind="stage_band", entry=self.band())
        assert "3" in verify_corpus(corpus).verified_entry_ids

    def test_refuses_a_threshold_whose_quote_is_not_in_the_order(self, corpus):
        """The whole hazard in one test: a plausible band with nothing behind it."""
        with pytest.raises(QuoteNotFound, match="page 2"):
            add_entry(
                corpus_root=corpus,
                kind="stage_band",
                entry=self.band(quote="Stage III applies above AQI 200"),
            )
        written = read_json(corpus / "stage_bands" / "grap_stage_bands.json")["stage_bands"]
        assert written == []

    def test_refuses_a_band_with_no_citation_at_all(self, corpus):
        broken = self.band()
        del broken["quote"]
        with pytest.raises(EntryRejected, match="quote"):
            add_entry(corpus_root=corpus, kind="stage_band", entry=broken)


class TestCli:
    def test_ingest_reports_the_hash_it_recorded(self, tmp_path, pdf, capsys):
        code = main(
            [
                "ingest",
                "--corpus",
                str(tmp_path / "corpus"),
                "--pdf",
                str(pdf),
                "--doc-id",
                "order-a",
                "--url",
                URL,
            ]
        )
        out = capsys.readouterr().out
        assert code == CorpusExit.OK
        assert hashlib.sha256(pdf.read_bytes()).hexdigest()[:12] in out

    def test_quote_not_found_exits_with_its_own_code_and_says_why(self, tmp_path, pdf, capsys):
        corpus = tmp_path / "corpus"
        ingest_document(corpus_root=corpus, pdf_path=pdf, doc_id="order-a", source_url=URL)
        payload = tmp_path / "entry.json"
        payload.write_text(
            json.dumps(
                {
                    "obligation_id": "grap3-dust-01",
                    "entity_types": ["construction_site"],
                    "triggers_at_stage": 3,
                    "label": "Suspend dust-generating activity",
                    "field": "has_dust_generating_activity",
                    "operator": "eq",
                    "value": True,
                    "source_doc": "order-a",
                    "page": 1,
                    "quote": "dust-generating work must stop",
                    "consequence": {"issues_parchi": True},
                }
            ),
            encoding="utf-8",
        )
        code = main(["add-obligation", "--corpus", str(corpus), "--file", str(payload)])
        combined = capsys.readouterr()
        assert code == CorpusExit.QUOTE_NOT_FOUND
        assert "verbatim" in (combined.out + combined.err).lower()

    def test_an_unknown_subcommand_is_a_usage_error_not_a_traceback(self, capsys):
        assert main(["frobnicate"]) == CorpusExit.USAGE

    def test_no_arguments_prints_usage(self, capsys):
        assert main([]) == CorpusExit.USAGE
        assert "ingest" in capsys.readouterr().out
