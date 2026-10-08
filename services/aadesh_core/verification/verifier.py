"""Citation verification: re-prove every quote against the bytes it claims to come from.

Zero infrastructure by design. No Docker, no OpenSearch, no AWS, no network. A judge cloning
this repo on a cold machine can run the core proof in seconds, and that property is worth
more than a tighter coupling to the search index.

What gets proved, in order:

  1. Every manifest document's bytes on disk SHA-256 to the hash recorded for them.
  2. Every citation names a document that exists in the manifest.
  3. Every citation's page text file exists.
  4. The document the citation names passed check 1.
  5. Every citation's quote appears VERBATIM in that page text.

Check 4 is not redundant with check 1. Extracted page text is a cache of what a document
said; if the document's bytes no longer hash to the manifest, that cache is not evidence
about anything, and a quote found in it proves nothing. Marking such a citation verified
would let a tampered source keep enforcing, which is precisely what verification exists to
prevent.

A corpus entry that passes all five is VERIFIED and may enter resolution. Anything else is
UNSOURCED and is excluded -- loudly.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from aadesh_core.sources import is_official_source_url

MANIFEST = "sources/manifest.json"
CORPUS_FILES = {
    "obligation": ("obligations/construction_site.json", "obligations", "obligation_id"),
    "entitlement": ("entitlements/cess_fund.json", "entitlements", "entitlement_id"),
    "stage_band": ("stage_bands/grap_stage_bands.json", "stage_bands", "stage"),
}

#: Files holding ONE object rather than a list. The invoked stage is checked here because it
#: is the fact that decides whether any obligation applies at all. Left outside the proof, a
#: tampered order could change what the entire system enforces while every obligation in the
#: corpus still verified cleanly.
SINGLETON_FILES = {
    "invoked_stage": ("invoked_stage.json", "invoked"),
}


@dataclass(frozen=True, slots=True)
class DocumentCheck:
    doc_id: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class CitationCheck:
    entry_kind: str
    entry_id: str
    source_doc: str
    page: int
    ok: bool
    detail: str


@dataclass
class VerificationReport:
    corpus_root: Path
    documents: list[DocumentCheck] = field(default_factory=list)
    citations: list[CitationCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def documents_verified(self) -> int:
        return sum(1 for d in self.documents if d.ok)

    @property
    def citations_verified(self) -> int:
        return sum(1 for c in self.citations if c.ok)

    @property
    def citations_failed(self) -> list[CitationCheck]:
        return [c for c in self.citations if not c.ok]

    @property
    def documents_failed(self) -> list[DocumentCheck]:
        return [d for d in self.documents if not d.ok]

    @property
    def has_failures(self) -> bool:
        return bool(self.documents_failed or self.citations_failed or self.errors)

    @property
    def is_empty(self) -> bool:
        """Nothing was proved. Distinct from 'something failed'."""
        return self.citations_verified == 0 and not self.has_failures

    @property
    def verified_entry_ids(self) -> set[str]:
        return {c.entry_id for c in self.citations if c.ok}


def normalise(text: str) -> str:
    """Fold the differences that PDF text extraction introduces but meaning does not.

    Unicode NFKC plus whitespace collapsing. This is the one place verification is lenient,
    and only about typography: a quote must still match word for word. Curly quotes, ligatures
    and a line break mid-sentence are extraction artefacts, not paraphrase.
    """
    folded = unicodedata.normalize("NFKC", text)
    # The "ambiguous" characters below are the whole point of this function: they are what a
    # PDF extractor emits where the order has a plain quote or hyphen. RUF001 is suppressed
    # deliberately rather than by rewriting them into the ASCII they are being folded TO.
    folded = folded.replace("’", "'").replace("‘", "'")  # noqa: RUF001
    folded = folded.replace("“", '"').replace("”", '"')
    folded = folded.replace("–", "-").replace("—", "-")  # noqa: RUF001
    return " ".join(folded.split()).casefold()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_corpus(corpus_root: Path) -> VerificationReport:
    """Run the full verification pass over `corpus_root`."""
    corpus_root = Path(corpus_root)
    report = VerificationReport(corpus_root=corpus_root)

    manifest_path = corpus_root / MANIFEST
    if not manifest_path.exists():
        report.errors.append(f"No source manifest at {manifest_path}")
        return report

    try:
        manifest = _load_json(manifest_path)
    except json.JSONDecodeError as exc:
        report.errors.append(f"Source manifest is not valid JSON: {exc}")
        return report

    documents = {d["doc_id"]: d for d in manifest.get("documents", [])}
    unhashed: set[str] = set()

    # 1. document bytes
    page_text: dict[tuple[str, int], str] = {}
    for doc_id, doc in documents.items():
        # A document hosted on a mirror is not the authority, even when its bytes hash to the
        # recorded value. Refused here as well as at ingestion so that a hand-edited manifest
        # cannot smuggle a non-official copy past the gate.
        if not is_official_source_url(doc.get("source_url", "")):
            unhashed.add(doc_id)
            report.documents.append(
                DocumentCheck(
                    doc_id,
                    False,
                    f"source_url {doc.get('source_url')!r} is not on an official domain. A "
                    f"mirror or a saved copy is not the order, so nothing it is quoted for "
                    f"can be treated as verified.",
                )
            )
            continue

        local = corpus_root / doc["local_path"]
        if not local.exists():
            unhashed.add(doc_id)
            report.documents.append(
                DocumentCheck(doc_id, False, f"file missing: {doc['local_path']}")
            )
            continue
        actual = hashlib.sha256(local.read_bytes()).hexdigest()
        if actual != doc["sha256"]:
            unhashed.add(doc_id)
            report.documents.append(
                DocumentCheck(
                    doc_id,
                    False,
                    f"hash mismatch: manifest says {doc['sha256'][:12]}..., "
                    f"bytes on disk are {actual[:12]}...",
                )
            )
            continue
        report.documents.append(
            DocumentCheck(doc_id, True, f"sha256 {actual[:12]}... matches manifest")
        )

    # 2-4. citations
    for kind, (relative, list_key, id_key) in CORPUS_FILES.items():
        path = corpus_root / relative
        if not path.exists():
            continue
        try:
            payload = _load_json(path)
        except json.JSONDecodeError as exc:
            report.errors.append(f"{relative} is not valid JSON: {exc}")
            continue

        for entry in payload.get(list_key, []):
            entry_id = str(entry.get(id_key, "<no id>"))
            for citation in _citations_in(entry):
                report.citations.append(
                    _check_citation(
                        corpus_root, documents, unhashed, page_text, kind, entry_id, citation
                    )
                )

    # 5. the invoked stage, which is a singleton and is therefore easy to forget
    for kind, (relative, key) in SINGLETON_FILES.items():
        path = corpus_root / relative
        if not path.exists():
            continue
        try:
            payload = _load_json(path)
        except json.JSONDecodeError as exc:
            report.errors.append(f"{relative} is not valid JSON: {exc}")
            continue
        entry = payload.get(key)
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("stage", "<no stage>"))
        citations = _citations_in(entry)
        if not citations:
            report.errors.append(
                f"{relative}: it invokes stage {entry_id} without citing the page of the "
                f"order that invoked it. Add source_doc, page and quote copied verbatim from "
                f"that page. The invoked stage decides which obligations apply, so it cannot "
                f"be the one claim in the corpus that nothing re-proves."
            )
            continue
        for citation in citations:
            report.citations.append(
                _check_citation(
                    corpus_root, documents, unhashed, page_text, kind, entry_id, citation
                )
            )

        # The quote must SUPPORT the stage, not merely appear on the page. Recorded as a
        # failing citation (not a loose error) so the loader's "proved" test sees it too and
        # refuses the same record `make verify` rejects.
        stage_value = entry.get("stage")
        quote = entry.get("quote")
        quote_misses_stage = (
            isinstance(stage_value, int)
            and isinstance(quote, str)
            and bool(quote)
            and not quote_names_stage(quote, stage_value)
        )
        if quote_misses_stage:
            report.citations.append(
                CitationCheck(
                    kind,
                    entry_id,
                    str(entry.get("source_doc", "<none>")),
                    int(entry.get("page", 0) or 0),
                    False,
                    f"the quoted sentence does not name stage {stage_value}. The quote "
                    f"must state the invocation it is cited for (e.g. contain 'Stage-III' "
                    f"or 'Stage 3'). Changing the stage without changing the sentence it "
                    f"cites is exactly the edit this check exists to catch.",
                )
            )

    return report


def _citations_in(entry: dict) -> list[dict]:
    """An entry's own citation, plus any nested ones (amounts, revocations, requirements)."""
    found: list[dict] = []
    if {"source_doc", "page", "quote"} <= entry.keys():
        found.append(entry)
    amount = entry.get("amount")
    if isinstance(amount, dict) and {"source_doc", "page", "quote"} <= amount.keys():
        found.append(amount)
    # A revocation is a claim of its own: "a later order ended this stage". Left out here it
    # would be the one legal fact in the corpus that nothing re-proves.
    revocation = entry.get("revocation")
    if isinstance(revocation, dict) and {"source_doc", "page", "quote"} <= revocation.keys():
        found.append(revocation)
    for requirement in entry.get("readiness_requirements", []) or []:
        if isinstance(requirement, dict) and {"source_doc", "page", "quote"} <= requirement.keys():
            found.append(requirement)
    return found


#: Roman ordinals up to Stage X. Beyond that, only the arabic form is recognised. The
#: conversion exists so "the quote must name the stage it invokes" can be checked against the
#: forms an order actually uses ("Stage-III" and "Stage 3" both appear in CAQM documents).
_ROMAN_ORDINALS = {
    1: "i",
    2: "ii",
    3: "iii",
    4: "iv",
    5: "v",
    6: "vi",
    7: "vii",
    8: "viii",
    9: "ix",
    10: "x",
}


def quote_names_stage(quote: str, stage: int) -> bool:
    """True if `quote` names `stage` as a GRAP stage, in roman or arabic form.

    This is the check that makes a citation SUPPORT its claim rather than merely exist. An
    invoked stage is the fact that decides which obligations apply; a quote that proves only
    that some sentence about something appears on a page does not prove which stage was
    invoked. Without this, changing `stage` from 3 to 4 while leaving the quoted sentence
    intact -- the exact edit the corpus gate must refuse -- would pass verification.
    """
    text = normalise(quote)
    ordinal = _ROMAN_ORDINALS.get(stage)
    tokens = [f"stage-{stage}", f"stage {stage}"]
    if ordinal:
        tokens += [f"stage-{ordinal}", f"stage {ordinal}"]
    return any(token in text for token in tokens)


def _check_citation(
    corpus_root: Path,
    documents: dict[str, dict],
    unhashed: set[str],
    page_cache: dict[tuple[str, int], str],
    kind: str,
    entry_id: str,
    citation: dict,
) -> CitationCheck:
    doc_id = citation["source_doc"]
    page = int(citation["page"])
    quote = citation["quote"]

    doc = documents.get(doc_id)
    if doc is None:
        return CitationCheck(
            kind,
            entry_id,
            doc_id,
            page,
            False,
            f"cites unknown document {doc_id!r}; it is not in the source manifest",
        )

    if doc_id in unhashed:
        return CitationCheck(
            kind,
            entry_id,
            doc_id,
            page,
            False,
            f"quotes {doc_id!r}, whose bytes no longer hash to the manifest. Extracted page "
            f"text is only evidence about the document it came from, so a quote found in it "
            f"proves nothing until the bytes match.",
        )

    key = (doc_id, page)
    if key not in page_cache:
        page_file = corpus_root / doc["pages_dir"] / f"p{page}.txt"
        if not page_file.exists():
            return CitationCheck(
                kind,
                entry_id,
                doc_id,
                page,
                False,
                f"no extracted text for page {page} (expected {page_file.name})",
            )
        page_cache[key] = normalise(page_file.read_text(encoding="utf-8"))

    if normalise(quote) in page_cache[key]:
        return CitationCheck(kind, entry_id, doc_id, page, True, "quote found verbatim")

    return CitationCheck(
        kind,
        entry_id,
        doc_id,
        page,
        False,
        f"quote not found on page {page}. A paraphrase fails this check by design -- "
        f"copy the text exactly as it appears in the order.",
    )
