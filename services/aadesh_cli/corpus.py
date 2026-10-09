"""`aadesh-corpus` -- the only sanctioned way bytes and clauses enter the corpus.

Hand-editing `corpus/` is how a paraphrased quote, a stale order, or an invented rupee figure
gets in. This CLI makes the two dangerous steps mechanical:

    ingest        hash the bytes you downloaded, store them, extract page text, record
                  where it came from and when
    add-obligation / add-entitlement
                  accept a clause ONLY if its `quote` is found verbatim on the page it cites

The quote check calls the SAME `normalise` the verifier calls. That is the load-bearing
detail: a writer more lenient than the verifier would accept entries `make verify` later
rejects, and a writer stricter than it would reject entries that are actually fine. One
definition, two callers.

Exit codes, distinct for the same reason `make verify`'s are -- the reaction differs:

    0  OK                 written
    1  USAGE              bad arguments or unknown subcommand
    2  SOURCE_REJECTED    the document is not usable (not a PDF, no text, id taken, bad id)
    3  QUOTE_NOT_FOUND    a quote is not where it claims to be. The important refusal.
    4  ENTRY_REJECTED     the entry is structurally wrong, or cites something absent

Usage:
    python -m aadesh_cli.corpus ingest --pdf ~/Downloads/order.pdf \\
        --doc-id caqm-grap-2026-01 --url https://caqm.nic.in/... --publisher CAQM
    python -m aadesh_cli.corpus add-obligation --file obligation.json
    python -m aadesh_cli.corpus add-entitlement --file entitlement.json
    python -m aadesh_cli.corpus add-stage-band --file band.json
    python -m aadesh_cli.corpus invoke-stage --stage 3 --doc-id caqm-grap-2026-01
        --page 2 --quote "the Commission hereby invokes GRAP Stage III"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

from aadesh_adapters.corpus.local_file import (
    reject_self_declared_provenance,
    validate_entry,
)
from aadesh_adapters.sources.pdf_text import SourceExtractionError, extract_pages
from aadesh_core.citations import labelled_citations, page_text_sha256
from aadesh_core.errors import AadeshError, CorpusIntegrityError
from aadesh_core.sources import is_official_source_url
from aadesh_core.verification import normalise

DEFAULT_CORPUS = Path("corpus")
MANIFEST = "sources/manifest.json"

#: doc_id becomes a filename, so it is validated as one. Traversal here would write outside
#: the corpus, and a doc_id with a slash would scatter one document across two directories.
DOC_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

CITATION_KEYS = {"source_doc", "page", "quote"}

#: kind -> (corpus-relative file, list key, id key, schema file)
KINDS: dict[str, tuple[str, str, str, str]] = {
    "obligation": (
        "obligations/construction_site.json",
        "obligations",
        "obligation_id",
        "obligation.schema.json",
    ),
    "entitlement": (
        "entitlements/cess_fund.json",
        "entitlements",
        "entitlement_id",
        "entitlement.schema.json",
    ),
    # AQI thresholds. Listed here for the same reason the stage_band schema exists: this is
    # the one place they may live, so this is the one place they must be quoted from a page.
    "stage_band": (
        "stage_bands/grap_stage_bands.json",
        "stage_bands",
        "stage",
        "stage_band.schema.json",
    ),
}

INVOKED_STAGE_FILE = "invoked_stage.json"


class CorpusExit(IntEnum):
    OK = 0
    USAGE = 1
    SOURCE_REJECTED = 2
    QUOTE_NOT_FOUND = 3
    ENTRY_REJECTED = 4


class IngestError(AadeshError):
    """Base for anything this CLI refuses to write."""


class SourceRejected(IngestError):
    """The document itself is not usable as a source."""


class QuoteNotFound(IngestError):
    """A quote is not present verbatim on the page it claims."""


class EntryRejected(IngestError):
    """The entry is structurally invalid, or cites something that is not in the corpus."""


class UsageError(AadeshError):
    """Bad arguments. Raised in place of argparse's SystemExit so main() can return a code."""


@dataclass(frozen=True, slots=True)
class IngestedDocument:
    doc_id: str
    sha256: str
    byte_size: int
    page_count: int
    local_path: str
    pages_dir: str


# --- ingestion -------------------------------------------------------------


def ingest_document(
    *,
    corpus_root: Path,
    pdf_path: Path,
    doc_id: str,
    source_url: str,
    title: str = "",
    publisher: str = "",
    retrieved_at: str | None = None,
) -> IngestedDocument:
    """Hash and store a downloaded document, extracting one text file per page.

    Everything that can reject the document happens BEFORE anything is written, so a refused
    ingest leaves the corpus exactly as it found it. Nothing is recorded that was not hashed
    from the bytes on disk at that moment.
    """
    corpus_root = Path(corpus_root)
    pdf_path = Path(pdf_path)

    if not DOC_ID_RE.match(doc_id or ""):
        raise SourceRejected(
            f"doc_id {doc_id!r} is not a kebab-case slug (lowercase letters, digits and "
            f"single hyphens, e.g. caqm-grap-2026-01). It becomes a filename, so anything "
            f"with a slash, a space or a dot in it is refused."
        )

    if not is_official_source_url(source_url):
        raise SourceRejected(
            f"source_url {source_url!r} is not on an official CAQM domain. A mirror, a news "
            f"article or a saved copy is not the order -- even when the bytes match, the copy "
            f"is not the authority. Download the document from the Commission itself and "
            f"record that URL."
        )

    if not pdf_path.exists():
        raise SourceRejected(
            f"no such file: {pdf_path}. Download the order from the official domain first. "
            f"An order you did not download is an order you cannot cite."
        )

    data = pdf_path.read_bytes()

    try:
        pages = extract_pages(data)
    except SourceExtractionError as exc:
        raise SourceRejected(f"{pdf_path.name}: {exc}") from exc

    documents = _read_manifest(corpus_root)
    if any(d.get("doc_id") == doc_id for d in documents):
        raise SourceRejected(
            f"{doc_id!r} is already in {MANIFEST}. Re-ingesting would replace bytes that "
            f"existing citations are checked against, silently orphaning them. Choose a new "
            f"doc_id (a revision is a new document: caqm-grap-2026-01-rev2), or remove the "
            f"entries that cite it first."
        )

    sha256 = hashlib.sha256(data).hexdigest()
    local_path = f"sources/{doc_id}.pdf"
    pages_dir = f"sources/pages/{doc_id}"

    destination = corpus_root / local_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    page_dir = corpus_root / pages_dir
    page_dir.mkdir(parents=True, exist_ok=True)
    for number, text in enumerate(pages, start=1):
        (page_dir / f"p{number}.txt").write_text(text, encoding="utf-8")

    documents.append(
        {
            "doc_id": doc_id,
            "title": title or doc_id,
            "publisher": publisher,
            "source_url": source_url,
            "retrieved_at": retrieved_at or datetime.now(UTC).isoformat(),
            "sha256": sha256,
            "byte_size": len(data),
            "local_path": local_path,
            "pages_dir": pages_dir,
            "page_sha256": {
                str(number): page_text_sha256(text) for number, text in enumerate(pages, start=1)
            },
        }
    )
    _write_manifest(corpus_root, documents)

    return IngestedDocument(
        doc_id=doc_id,
        sha256=sha256,
        byte_size=len(data),
        page_count=len(pages),
        local_path=local_path,
        pages_dir=pages_dir,
    )


# --- adding clauses --------------------------------------------------------


def add_entry(*, corpus_root: Path, kind: str, entry: dict[str, Any]) -> Path:
    """Append one obligation or entitlement, after proving every quote in it.

    Order of checks matters. Provenance is checked first because an entry declaring itself
    verified must never reach a validator that would happily accept the extra key. Then the
    schema, so a structurally broken entry fails with the field name rather than a confusing
    quote error. Then the quotes, which is the check that actually protects the claim.
    """
    corpus_root = Path(corpus_root)
    if kind not in KINDS:
        raise EntryRejected(f"unknown entry kind {kind!r}; expected one of {sorted(KINDS)}")
    relative, list_key, id_key, schema_name = KINDS[kind]

    entry = dict(entry)
    entry_id = str(entry.get(id_key, "<no id>"))
    where = f"{relative} ({entry_id})"

    try:
        # Same two functions the loader uses, so an entry this CLI accepts cannot be one the
        # loader refuses -- the writer and the reader share one definition of "well formed".
        reject_self_declared_provenance(entry, where)
        amount = entry.get("amount")
        if isinstance(amount, dict):
            reject_self_declared_provenance(amount, f"{where} amount")
        validate_entry(entry, schema_name)
    except CorpusIntegrityError as exc:
        raise EntryRejected(str(exc)) from exc

    documents = {d["doc_id"]: d for d in _read_manifest(corpus_root)}
    for label, citation in _labelled_citations(entry):
        _require_quote_on_page(
            corpus_root=corpus_root,
            documents=documents,
            entry_id=entry_id,
            label=label,
            citation=citation,
        )

    existing = _read_entries(corpus_root, relative, list_key)
    if any(str(e.get(id_key)) == entry_id for e in existing):
        raise EntryRejected(
            f"{relative}: {entry_id!r} already exists. Editing a clause in place would mean "
            f"the corpus no longer matches the run that produced earlier parchis. Supersede "
            f"it with a new id instead."
        )

    existing.append(entry)
    path = corpus_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({list_key: existing}, indent=2) + "\n", encoding="utf-8")
    return path


def _labelled_citations(entry: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """An entry's citations, each labelled so a failure can say WHICH one is unfound."""
    return labelled_citations(entry)


def _require_quote_on_page(
    *,
    corpus_root: Path,
    documents: dict[str, dict[str, Any]],
    entry_id: str,
    label: str,
    citation: dict[str, Any],
) -> None:
    doc_id = str(citation["source_doc"])
    page = int(citation["page"])
    quote = str(citation["quote"])

    document = documents.get(doc_id)
    if document is None:
        raise EntryRejected(
            f"{entry_id}: the {label} cites document {doc_id!r}, which is not in {MANIFEST}. "
            f"Ingest the order first -- a citation to a document nobody has hashed cannot be "
            f"re-proved."
        )

    page_file = corpus_root / document["pages_dir"] / f"p{page}.txt"
    if not page_file.exists():
        raise EntryRejected(
            f"{entry_id}: the {label} cites page {page} of {doc_id!r}, but no extracted text "
            f"exists for that page (expected {page_file}). Check the page number, or ingest "
            f"the document again."
        )

    source_path = corpus_root / document["local_path"]
    if (
        not source_path.exists()
        or hashlib.sha256(source_path.read_bytes()).hexdigest() != document["sha256"]
    ):
        raise EntryRejected(f"{entry_id}: source {doc_id!r} no longer hashes to its manifest")
    raw_text = page_file.read_text(encoding="utf-8")
    if document.get("page_sha256", {}).get(str(page)) != page_text_sha256(raw_text):
        raise EntryRejected(f"{entry_id}: extracted page {page} hash is missing or mismatched")
    if normalise(quote) in normalise(raw_text):
        return

    raise QuoteNotFound(
        f"{entry_id}: the {label}'s quote is not on page {page} of {doc_id!r}. The quote must "
        f"appear VERBATIM in the extracted text of the page it cites. A paraphrase fails "
        f"here by design: it is the only thing standing between a remembered rule and a "
        f"cited one. Open {page_file.name} and copy the sentence exactly."
    )


# --- manifest and corpus file IO ------------------------------------------


def _read_manifest(corpus_root: Path) -> list[dict[str, Any]]:
    path = Path(corpus_root) / MANIFEST
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("documents", []))


def _write_manifest(corpus_root: Path, documents: list[dict[str, Any]]) -> None:
    path = Path(corpus_root) / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"documents": documents}, indent=2) + "\n", encoding="utf-8")


def _read_entries(corpus_root: Path, relative: str, list_key: str) -> list[dict[str, Any]]:
    path = Path(corpus_root) / relative
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get(list_key, []))


# --- CLI -------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """argparse that raises instead of calling sys.exit, so main() can return a code."""

    def error(self, message: str):
        raise UsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="aadesh-corpus",
        description=(
            "Add a source document or a cited clause to the corpus. This is the only "
            "sanctioned way in: every quote is checked verbatim against the page it cites."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest", help="hash and store a downloaded source document")
    ingest.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ingest.add_argument("--pdf", required=True, help="the exact bytes you downloaded")
    ingest.add_argument("--doc-id", required=True, help="kebab-case; becomes the filename")
    ingest.add_argument("--url", required=True, help="the official URL it came from")
    ingest.add_argument("--title", default="")
    ingest.add_argument("--publisher", default="")
    ingest.add_argument("--retrieved-at", default=None, help="ISO-8601. Defaults to now (UTC).")

    for name, kind in (
        ("add-obligation", "obligation"),
        ("add-entitlement", "entitlement"),
        ("add-stage-band", "stage_band"),
    ):
        add = sub.add_parser(name, help=f"add a cited {kind} to the corpus")
        add.add_argument("--corpus", default=str(DEFAULT_CORPUS))
        add.add_argument("--file", required=True, help="JSON file holding one entry")

    invoke = sub.add_parser(
        "invoke-stage", help="record the stage an order has invoked, quoting the order"
    )
    invoke.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    invoke.add_argument("--stage", required=True, type=int)
    invoke.add_argument("--doc-id", required=True, help="the order that invoked it")
    invoke.add_argument("--page", required=True, type=int)
    invoke.add_argument("--quote", required=True, help="verbatim, from that page")
    invoke.add_argument("--invoked-at", default=None, help="ISO-8601. Defaults to now (UTC).")
    invoke.add_argument(
        "--lifecycle",
        choices=["active", "revoked"],
        default="active",
        help="'revoked' records a HISTORICAL invocation that must also cite its revocation",
    )
    invoke.add_argument("--revocation-doc-id", default=None, help="the order that revoked it")
    invoke.add_argument("--revocation-page", type=int, default=None)
    invoke.add_argument("--revocation-quote", default=None, help="verbatim, from that page")
    invoke.add_argument("--revoked-at", default=None, help="ISO-8601 instant of revocation")
    invoke.add_argument("--note", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("", file=sys.stderr)
        parser.print_help(sys.stderr)
        return CorpusExit.USAGE

    if not args.command:
        parser.print_help()
        return CorpusExit.USAGE

    try:
        if args.command == "ingest":
            _do_ingest(args)
        elif args.command == "invoke-stage":
            _do_invoke(args)
        else:
            _do_add(args, ADD_COMMANDS[args.command])
    except QuoteNotFound as exc:
        print(f"REFUSED -- quote not found\n\n  {exc}\n", file=sys.stderr)
        return CorpusExit.QUOTE_NOT_FOUND
    except EntryRejected as exc:
        print(f"REFUSED -- entry rejected\n\n  {exc}\n", file=sys.stderr)
        return CorpusExit.ENTRY_REJECTED
    except SourceRejected as exc:
        print(f"REFUSED -- source rejected\n\n  {exc}\n", file=sys.stderr)
        return CorpusExit.SOURCE_REJECTED
    return CorpusExit.OK


ADD_COMMANDS = {
    "add-obligation": "obligation",
    "add-entitlement": "entitlement",
    "add-stage-band": "stage_band",
}


def invoke_stage(
    *,
    corpus_root: Path,
    stage: int,
    source_doc: str,
    page: int,
    quote: str,
    invoked_at: str | None = None,
    note: str = "",
    lifecycle: str = "active",
    revocation: dict[str, Any] | None = None,
) -> Path:
    """Record which stage an order has invoked, with the sentence that invoked it.

    This is the fact the whole system hangs on: no invoked stage, no applicable obligation.
    So it is written the same way everything else is -- quoted, checked, and refused if the
    quote is not where it says it is.

    Pass ``lifecycle="revoked"`` together with a ``revocation`` citation to record a stage
    that a later order ended. That record is HISTORICAL: the loader will not hand it to the
    resolver as the live stage, so a revoked invocation can never keep enforcing.
    """
    corpus_root = Path(corpus_root)
    if stage < 1:
        raise EntryRejected(f"stage {stage} is not a stage ordinal; expected an integer >= 1")
    if lifecycle not in ("active", "revoked"):
        raise EntryRejected(
            f"lifecycle {lifecycle!r} is not 'active' or 'revoked'. Which of the two a record "
            f"is decides whether it is treated as current, so it may not be guessed."
        )

    payload = {
        "stage": int(stage),
        "source_doc": source_doc,
        "page": int(page),
        "quote": quote,
        "invoked_at": invoked_at or datetime.now(UTC).isoformat(),
    }
    if lifecycle == "revoked":
        if not revocation:
            raise EntryRejected(
                "a revoked invocation must carry its own revocation citation (source_doc, "
                "page and quote from the later order). 'It was revoked' is a legal fact like "
                "any other and cannot be taken on trust."
            )
        payload["lifecycle"] = "revoked"
        payload["revocation"] = {
            "source_doc": revocation["source_doc"],
            "page": int(revocation["page"]),
            "quote": revocation["quote"],
            "revoked_at": revocation.get("revoked_at") or datetime.now(UTC).isoformat(),
        }
    if note:
        payload["note"] = note

    documents = {d["doc_id"]: d for d in _read_manifest(corpus_root)}
    _require_quote_on_page(
        corpus_root=corpus_root,
        documents=documents,
        entry_id=f"invoked stage {stage}",
        label="invocation",
        citation=payload,
    )

    try:
        validate_entry(payload, "invoked_stage.schema.json")
    except CorpusIntegrityError as exc:
        raise EntryRejected(str(exc)) from exc

    path = corpus_root / INVOKED_STAGE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"invoked": payload}, indent=2) + "\n", encoding="utf-8")
    return path


def _do_invoke(args: argparse.Namespace) -> None:
    revocation = None
    if args.lifecycle == "revoked":
        if not (args.revocation_doc_id and args.revocation_page and args.revocation_quote):
            raise EntryRejected(
                "--lifecycle revoked requires --revocation-doc-id, --revocation-page and "
                "--revocation-quote. A revocation with no citation is an assertion, and the "
                "whole point of this corpus is that assertions do not enter it."
            )
        revocation = {
            "source_doc": args.revocation_doc_id,
            "page": args.revocation_page,
            "quote": args.revocation_quote,
            "revoked_at": args.revoked_at,
        }

    written = invoke_stage(
        corpus_root=Path(args.corpus),
        stage=args.stage,
        source_doc=args.doc_id,
        page=args.page,
        quote=args.quote,
        invoked_at=args.invoked_at,
        note=args.note,
        lifecycle=args.lifecycle,
        revocation=revocation,
    )
    print(f"WROTE invoked stage -> {written}")
    print("")
    print("  Run `make verify`. The invoked stage now has to re-prove its own citation.")


def _do_ingest(args: argparse.Namespace) -> None:
    result = ingest_document(
        corpus_root=Path(args.corpus),
        pdf_path=Path(args.pdf),
        doc_id=args.doc_id,
        source_url=args.url,
        title=args.title,
        publisher=args.publisher,
        retrieved_at=args.retrieved_at,
    )
    print("INGESTED")
    print(f"  doc_id           : {result.doc_id}")
    print(f"  sha256           : {result.sha256}")
    print(f"  bytes            : {result.byte_size}")
    print(f"  pages extracted  : {result.page_count}")
    print(f"  stored at        : {result.local_path}")
    print(f"  page text under  : {result.pages_dir}/p<N>.txt")
    print("")
    print("  Next: cite a clause from one of those page files, quoting VERBATIM.")
    print("  Nothing in this document is verified until `make verify` re-proves it.")


def _do_add(args: argparse.Namespace, kind: str) -> None:
    path = Path(args.file)
    if not path.exists():
        raise EntryRejected(f"no such entry file: {path}")
    entry = json.loads(path.read_text(encoding="utf-8"))
    written = add_entry(corpus_root=Path(args.corpus), kind=kind, entry=entry)
    print(f"WROTE {kind} -> {written}")
    print("")
    print("  Run `make verify`. A quote the verifier cannot find is not yet a citation.")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
