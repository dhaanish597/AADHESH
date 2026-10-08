"""`make verify` -- the command that re-proves Aadesh's citations.

Verification is a command rather than a claim. Most projects that say "real data" cannot
show it; this one can, in seconds, with no infrastructure.

Exit codes are deliberately distinct, because "not finished yet" and "something is wrong"
need different reactions:

    0  OK                   every citation re-proved, and there was at least one
    1  FAILED               a hash mismatch or a quote that is not where it claims to be
    2  CORPUS_NOT_READY     zero verified citations -- nothing to prove yet
    3  TAMPER_UNPROVABLE    --tamper ran with no source documents to tamper with
    4  TAMPER_NOT_DETECTED  --tamper flipped a byte and verification still passed (alarm)

Note on `--tamper`: it reports FAILED and exits non-zero when it works correctly. That reads
backwards for a second, so it says so on screen. The failure IS the proof -- a hash check
that has never failed proves only that you did not delete your files.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from enum import IntEnum
from pathlib import Path
from typing import TextIO

from aadesh_core.verification import VerificationReport, verify_corpus

DEFAULT_CORPUS = Path("corpus")


class VerifyExit(IntEnum):
    OK = 0
    FAILED = 1
    CORPUS_NOT_READY = 2
    TAMPER_UNPROVABLE = 3
    TAMPER_NOT_DETECTED = 4


NOT_READY_GUIDANCE = """
  Nothing in this corpus can enter obligation resolution yet, and no parchi can cite a
  legal basis. This is the expected Day 1 state and the gate is working as designed.

  To clear it, for EACH measure you intend to encode:

    1. Locate the CURRENT CAQM order on the official domain. Not a mirror, not a news PDF.
    2. Save the downloaded bytes to corpus/sources/<doc_id>.pdf and record the document in
       corpus/sources/manifest.json with its sha256, source_url and retrieved_at.
    3. Extract page text to corpus/sources/pages/<doc_id>/p<N>.txt, one file per page.
    4. Add the obligation / entitlement / stage band quoting VERBATIM from that page.

  Do NOT populate these files from memory, from a news article, or from a strategy
  document. GRAP has been revised repeatedly, with orders amending earlier orders. If you
  cannot establish which order is current for a measure, DROP THAT MEASURE. Ten certain
  obligations beat twenty-five uncertain ones -- a confidently wrong citation is worse than
  no citation, because provenance has been loudly advertised.
"""


def _print_report(report: VerificationReport, out: TextIO) -> None:
    print("AADESH CITATION VERIFICATION", file=out)
    print(f"corpus: {report.corpus_root}", file=out)
    print("", file=out)

    print("source documents", file=out)
    print(f"  manifest entries        : {len(report.documents)}", file=out)
    print(f"  bytes verified (sha-256): {report.documents_verified}", file=out)
    for doc in report.documents_failed:
        print(f"    FAIL {doc.doc_id}: {doc.detail}", file=out)
    print("", file=out)

    print("citations", file=out)
    print(f"  entries checked         : {len(report.citations)}", file=out)
    print(f"  verified verbatim       : {report.citations_verified}", file=out)
    print(f"  failed                  : {len(report.citations_failed)}", file=out)
    for citation in report.citations_failed:
        print(
            f"    FAIL {citation.entry_kind} {citation.entry_id} "
            f"[{citation.source_doc} p.{citation.page}]: {citation.detail}",
            file=out,
        )
    for error in report.errors:
        print(f"    ERROR {error}", file=out)
    print("", file=out)


def _classify(report: VerificationReport) -> VerifyExit:
    if report.has_failures:
        return VerifyExit.FAILED
    if report.citations_verified == 0:
        return VerifyExit.CORPUS_NOT_READY
    return VerifyExit.OK


def _run_plain(corpus_root: Path, out: TextIO) -> VerifyExit:
    report = verify_corpus(corpus_root)
    _print_report(report, out)
    code = _classify(report)

    if code is VerifyExit.OK:
        print(
            f"VERIFIED - {report.documents_verified} source object(s) and "
            f"{report.citations_verified} citation(s) re-proved against indexed source bytes.",
            file=out,
        )
    elif code is VerifyExit.CORPUS_NOT_READY:
        print("FAILED - corpus has zero verified citations.", file=out)
        print(NOT_READY_GUIDANCE, file=out)
        print(f"exit {int(code)} (CORPUS_NOT_READY)", file=out)
    else:
        print(
            "FAILED - one or more citations could not be re-proved against the bytes they cite.",
            file=out,
        )
        print(f"exit {int(code)} (FAILED)", file=out)
    return code


def _run_tamper(corpus_root: Path, out: TextIO) -> VerifyExit:
    """Flip one byte in a scratch COPY and assert verification catches it."""
    baseline = verify_corpus(corpus_root)
    target = next((d for d in baseline.documents), None)

    if target is None:
        print("AADESH TAMPER CHECK", file=out)
        print(f"corpus: {corpus_root}", file=out)
        print("", file=out)
        print(
            "CANNOT PROVE - there are no source documents in this corpus, so there is "
            "nothing to tamper with and this check demonstrates nothing.",
            file=out,
        )
        print(
            "  Add a hashed CAQM order first (see `make verify`), then run this again.",
            file=out,
        )
        print(f"exit {int(VerifyExit.TAMPER_UNPROVABLE)} (TAMPER_UNPROVABLE)", file=out)
        return VerifyExit.TAMPER_UNPROVABLE

    with tempfile.TemporaryDirectory(prefix="aadesh-tamper-") as scratch:
        scratch_corpus = Path(scratch) / "corpus"
        shutil.copytree(corpus_root, scratch_corpus)

        manifest_doc = _find_local_path(scratch_corpus, target.doc_id)
        data = bytearray(manifest_doc.read_bytes())
        original = data[0]
        data[0] = (original + 1) % 256
        manifest_doc.write_bytes(bytes(data))

        print("AADESH TAMPER CHECK", file=out)
        print(f"corpus: {corpus_root} (scratch copy; the real corpus is untouched)", file=out)
        print(
            f"flipped byte 0 of {target.doc_id}: 0x{original:02x} -> 0x{data[0]:02x}",
            file=out,
        )
        print("", file=out)

        report = verify_corpus(scratch_corpus)
        _print_report(report, out)

        if report.has_failures:
            print(
                "FAILED (expected) - the tampered byte was detected. The citation gate works.",
                file=out,
            )
            print(
                "  This command exits non-zero ON PURPOSE: the failure above IS the proof. "
                "A hash check that has never failed proves only that you did not delete "
                "your files.",
                file=out,
            )
            print(f"exit {int(VerifyExit.FAILED)} (FAILED, expected)", file=out)
            return VerifyExit.FAILED

    print(
        "CRITICAL - a tampered source document PASSED verification. "
        "The citation gate is not working and nothing it has ever reported can be trusted.",
        file=out,
    )
    print(f"exit {int(VerifyExit.TAMPER_NOT_DETECTED)} (TAMPER_NOT_DETECTED)", file=out)
    return VerifyExit.TAMPER_NOT_DETECTED


def _find_local_path(corpus_root: Path, doc_id: str) -> Path:
    import json

    manifest = json.loads((corpus_root / "sources" / "manifest.json").read_text(encoding="utf-8"))
    for doc in manifest["documents"]:
        if doc["doc_id"] == doc_id:
            return corpus_root / doc["local_path"]
    raise KeyError(doc_id)


def run_verify(
    *,
    corpus_root: Path = DEFAULT_CORPUS,
    tamper: bool = False,
    with_index: bool = False,
    stream: TextIO | None = None,
) -> VerifyExit:
    """Run verification. Returns the exit code rather than exiting, so tests can call it."""
    out = stream or sys.stdout
    if with_index:
        print(
            "NOTE: --with-index is not implemented yet. Running the zero-infra check only.",
            file=out,
        )
    if tamper:
        return _run_tamper(Path(corpus_root), out)
    return _run_plain(Path(corpus_root), out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aadesh-verify",
        description="Re-prove every cited quote against the hashed source bytes it claims.",
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--tamper",
        action="store_true",
        help="Flip a byte in a scratch copy and prove the check catches it.",
    )
    parser.add_argument(
        "--with-index",
        action="store_true",
        help="Additionally assert the OpenSearch index agrees (requires Docker).",
    )
    args = parser.parse_args(argv)
    return int(run_verify(corpus_root=args.corpus, tamper=args.tamper, with_index=args.with_index))


if __name__ == "__main__":
    raise SystemExit(main())
