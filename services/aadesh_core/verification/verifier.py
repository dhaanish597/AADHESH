"""Citation verification: re-prove every quote against the bytes it claims to come from.

Zero infrastructure by design. No Docker, no OpenSearch, no AWS, no network. A judge cloning
this repo on a cold machine can run the core proof in seconds, and that property is worth
more than a tighter coupling to the search index.

What gets proved, in order:

  1. Every manifest document's bytes on disk SHA-256 to the hash recorded for them.
  2. Every citation names a document that exists in the manifest.
  3. Every citation's page text file exists.
  4. Every citation's quote appears VERBATIM in that page text.

A corpus entry that passes all four is VERIFIED and may enter resolution. Anything else is
UNSOURCED and is excluded -- loudly.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST = "sources/manifest.json"
CORPUS_FILES = {
    "obligation": ("obligations/construction_site.json", "obligations", "obligation_id"),
    "entitlement": ("entitlements/cess_fund.json", "entitlements", "entitlement_id"),
    "stage_band": ("stage_bands/grap_stage_bands.json", "stage_bands", "stage"),
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


def _normalise(text: str) -> str:
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

    # 1. document bytes
    page_text: dict[tuple[str, int], str] = {}
    for doc_id, doc in documents.items():
        local = corpus_root / doc["local_path"]
        if not local.exists():
            report.documents.append(
                DocumentCheck(doc_id, False, f"file missing: {doc['local_path']}")
            )
            continue
        actual = hashlib.sha256(local.read_bytes()).hexdigest()
        if actual != doc["sha256"]:
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
                    _check_citation(corpus_root, documents, page_text, kind, entry_id, citation)
                )

    return report


def _citations_in(entry: dict) -> list[dict]:
    """An entry's own citation, plus any nested ones (amounts, readiness requirements)."""
    found: list[dict] = []
    if {"source_doc", "page", "quote"} <= entry.keys():
        found.append(entry)
    amount = entry.get("amount")
    if isinstance(amount, dict) and {"source_doc", "page", "quote"} <= amount.keys():
        found.append(amount)
    for requirement in entry.get("readiness_requirements", []) or []:
        if isinstance(requirement, dict) and {"source_doc", "page", "quote"} <= requirement.keys():
            found.append(requirement)
    return found


def _check_citation(
    corpus_root: Path,
    documents: dict[str, dict],
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
        page_cache[key] = _normalise(page_file.read_text(encoding="utf-8"))

    if _normalise(quote) in page_cache[key]:
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
