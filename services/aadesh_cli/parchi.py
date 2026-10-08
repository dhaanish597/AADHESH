"""`aadesh-parchi` -- the smallest end-to-end demonstration of the acknowledgement flow.

What this is: one command that opens a parchi for each displaced worker, hands out a QR,
shows what the worker sees, takes their confirmation, seals the record, and prints the audit
trail. It exists so that "a worker confirmed it and here is immutable evidence" is something a
reviewer can watch happen rather than take on trust.

What this is NOT, and the output says so on every screen:

  * It does NOT show a live CAQM invocation. The shipped corpus records exactly one invoked
    stage -- Stage III, invoked 16 January 2026 -- and CAQM REVOKED it on 22 January 2026. No
    stage is in force. This command replays that revoked invocation as history, with
    provenance=replay, and says "HISTORICAL REPLAY" where a reader might otherwise assume
    otherwise. There is no code path here that can manufacture a current invocation.
  * It does NOT compute an entitlement. There is no verified monetary amount in the corpus, so
    what is carried onto the record is references to cited clauses and nothing else.
  * It is NOT the API. Authorization, authentication and the Cedar boundary are elsewhere; this
    is the domain walking through its own states so you can see them.

The exit code is distinct for "there is no invocation on record to replay", because that is a
different situation from "the demo broke".
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import TextIO

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.domain import Provenance, StationReading
from aadesh_core.errors import AadeshError, TokenRejected, WrongWorker
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    Roster,
    RosterEntry,
    WorkflowExecution,
    create_parchi_for_worker,
)
from aadesh_core.parchi_ack.events import (
    EVENT_TYPE_PARCHI_ACKNOWLEDGED,
    EVENT_TYPE_PARCHI_SEALED,
)
from aadesh_core.parchi_ack.service import (
    acknowledge_parchi,
    describe_pending_parchi,
    seal_parchi,
)
from aadesh_core.parchi_ack.tokens import TOKEN_SCHEME

DEFAULT_CORPUS = Path("corpus")

#: A fixed clock. The demo is a replay, and a replay that printed a different time each run
#: could not be compared against the previous run's output.
DEMO_NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)

DEMO_SITE = "site-demo-001"

ROSTER = Roster(
    site_id=DEMO_SITE,
    entries=(
        RosterEntry(worker_id="worker-001", display_name="Worker A"),
        RosterEntry(worker_id="worker-002", display_name="Worker B"),
    ),
)


class ParchiExit(IntEnum):
    OK = 0
    NOTHING_TO_REPLAY = 2
    FAILED = 1


def _rule(out: TextIO, title: str) -> None:
    print("", file=out)
    print(f"--- {title} " + "-" * max(0, 68 - len(title)), file=out)


def _demo_provenance(corpus: LocalFileCorpus, invocation) -> ParchiProvenance:
    """The evidence a demo parchi rests on, all of it labelled replay or reference.

    The obligations are the REAL ones from the corpus -- the cited clauses that a halt at this
    stage would actually trigger. Nothing about them is invented for the demo.
    """
    obligations = tuple(
        o
        for o in corpus.obligations()
        if o.triggers_at_stage == invocation.stage and o.issues_parchi
    )
    entitlement_refs = tuple(
        sorted({o.worker_entitlement_ref for o in obligations if o.worker_entitlement_ref})
    )

    reading = StationReading(
        station_id="station-demo-replay",
        parameter="aqi",
        value=0.0,
        observed_at=invocation.invoked_at,
        ingested_at=invocation.invoked_at,
        provenance=Provenance.REPLAY,
    )

    return ParchiProvenance(
        stage=invocation,
        reading=reading,
        obligation_ids=tuple(sorted(o.obligation_id for o in obligations)),
        entitlement_refs=entitlement_refs,
        readiness_checklist=tuple(sorted(o.label for o in obligations)),
        displaced_worker_days=1,
    )


def _print_context(out: TextIO, corpus: LocalFileCorpus, invocation) -> None:
    live = corpus.invoked_stage()

    _rule(out, "1. What stage is in force RIGHT NOW")
    if live is None:
        print(
            "  No stage is currently in force. The corpus records no active CAQM "
            "invocation,\n  so nothing in this system is enforcing anything today, and this "
            "demo will not pretend otherwise.",
            file=out,
        )
    else:  # pragma: no cover -- would mean the corpus changed; the demo would still be honest
        print(f"  A stage IS in force: Stage {live.stage}.", file=out)

    _rule(out, "2. The invocation this demo replays")
    print("  HISTORICAL REPLAY -- this invocation is NOT in force.", file=out)
    print(f"    stage          : {invocation.stage}", file=out)
    print(f"    invoked at     : {invocation.invoked_at.isoformat()}", file=out)
    print(f"    lifecycle      : {invocation.lifecycle.value}", file=out)
    print(f"    source document: {invocation.order_doc_id}", file=out)
    print(f"    source sha-256 : {invocation.order_sha256}", file=out)
    if invocation.revocation_citation is not None:
        print(
            f"    revoked at     : "
            f"{invocation.revoked_at.isoformat() if invocation.revoked_at else 'n/a'}",
            file=out,
        )
        print(
            f"    revoked by     : {invocation.revocation_citation.source_doc} "
            f"p.{invocation.revocation_citation.page}",
            file=out,
        )
    print(
        "\n  Replaying this is the point: the record of what CAQM ordered in January is "
        "provable\n  and re-playable. It is not a claim that January's order still applies.",
        file=out,
    )


def _print_view(out: TextIO, view) -> None:
    _rule(out, "4. What the worker sees BEFORE confirming")
    print(f"    parchi         : {view.parchi_id}", file=out)
    print(f"    site           : {view.site_id}", file=out)
    print(f"    worker         : {view.worker_id}", file=out)
    print(f"    state          : {view.state.value}", file=out)
    print(f"    stage          : {view.stage}", file=out)
    print(f"    provenance     : {view.provenance.value if view.provenance else 'n/a'}", file=out)
    print(
        f"    backed by a live measurement: {'yes' if view.cites_measured_data else 'NO'}"
        "   <- this record is a replay",
        file=out,
    )
    print(f"    obligation refs: {', '.join(view.obligation_ids) or 'none'}", file=out)
    print(
        f"    entitlement refs: {', '.join(view.entitlement_refs) or 'none'}"
        "   (references to cited clauses; NO amount is computed anywhere)",
        file=out,
    )
    print("    checklist      :", file=out)
    for item in view.readiness_checklist:
        print(f"      - {item}", file=out)
    print(f"    link expires   : {view.expires_at.isoformat()}", file=out)
    print(
        "\n    Note what is absent: no Aadhaar, no phone number, no address, no bank "
        "details.\n    The record identifies the worker by an internal id and by nothing else.",
        file=out,
    )


def run_demo(*, corpus_root: Path = DEFAULT_CORPUS, stream: TextIO | None = None) -> ParchiExit:
    """Run the whole flow. Returns the exit code rather than exiting, so tests can call it."""
    out = stream or sys.stdout
    corpus = LocalFileCorpus(Path(corpus_root))

    print("AADESH PARCHI -- worker acknowledgement, end to end", file=out)
    print(
        "every fact below is either cited from the corpus or explicitly labelled replay",
        file=out,
    )

    history = corpus.invocation_history()
    if not history:
        print("", file=out)
        print(
            "NOTHING TO REPLAY -- the corpus records no invocation at all, so there is no "
            "stage\nthis demo could honestly use. Refusing rather than inventing one.",
            file=out,
        )
        return ParchiExit.NOTHING_TO_REPLAY

    invocation = history[0]
    _print_context(out, corpus, invocation)

    provenance = _demo_provenance(corpus, invocation)
    execution = WorkflowExecution(
        execution_id="exec-demo-001",
        site_id=DEMO_SITE,
        source_event_id=f"evt-replay-{invocation.order_doc_id}",
    )

    store = InMemoryParchiStore()
    tokens = InMemoryAcknowledgementTokenStore()
    ledger = InMemoryIdempotencyLedger()
    audit = RecordingAuditLog()

    _rule(out, "3. Opening one parchi per displaced worker")
    results = [
        create_parchi_for_worker(
            parchi_id=f"parchi-demo-{entry.worker_id}",
            execution=execution,
            worker=entry,
            provenance=provenance,
            idempotency_key=execution.idempotency_key_for(entry.worker_id),
            now=DEMO_NOW,
            store=store,
            tokens=tokens,
        )
        for entry in ROSTER.active_entries()
    ]
    for result in results:
        print(
            f"    {result.parchi.worker_id}: {result.parchi.parchi_id} "
            f"[{result.parchi.state.value}]",
            file=out,
        )

    subject = results[0]
    payload = subject.qr.payload

    print("", file=out)
    print("    the link handed to the first worker (this is the QR payload, verbatim):", file=out)
    print(f"      {payload}", file=out)
    print(
        "    it contains an opaque token and nothing else -- no worker id, no parchi id, no\n"
        "    site, no JSON. Everything it means is resolved server-side from its hash.",
        file=out,
    )

    _print_view(
        out,
        describe_pending_parchi(payload=payload, now=DEMO_NOW, store=store, tokens=tokens),
    )

    _rule(out, "5. The worker confirms their own parchi")
    outcome = acknowledge_parchi(
        payload=payload,
        actor_worker_id=subject.parchi.worker_id,
        now=DEMO_NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    )
    print(f"    state          : {outcome.parchi.state.value}", file=out)
    print(f"    acknowledged by: {outcome.parchi.acknowledged_by}", file=out)
    print(f"    method         : {outcome.parchi.acknowledgement_method.value}", file=out)
    print(f"    at             : {outcome.parchi.acknowledged_at.isoformat()}", file=out)
    print(f"    event          : {outcome.event.event_id}", file=out)
    print(
        "\n    Confirming is NOT sealing. The worker confirmed a fact; the system has not yet\n"
        "    frozen the record. Keeping those apart is what makes each separately provable.",
        file=out,
    )

    _rule(out, "6. Refusals -- what the system will NOT do")
    try:
        acknowledge_parchi(
            payload=payload,
            actor_worker_id="worker-002",
            now=DEMO_NOW,
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
        )
    except WrongWorker as exc:
        print("    a colleague tries to confirm someone else's parchi:", file=out)
        print(f"      REFUSED -- {exc}", file=out)

    try:
        acknowledge_parchi(
            payload=f"{TOKEN_SCHEME}{'A' * 43}",
            actor_worker_id=subject.parchi.worker_id,
            now=DEMO_NOW,
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
        )
    except TokenRejected as exc:
        print("    a forged link is presented:", file=out)
        print(f"      REFUSED -- {exc.message}", file=out)
        print(
            "      (the reason field says "
            f"{exc.reason.value!r}, but a caller is never shown it: an error that "
            "distinguished\n      forged from expired would be an oracle for guessing tokens)",
            file=out,
        )

    try:
        acknowledge_parchi(
            payload=payload,
            actor_worker_id=subject.parchi.worker_id,
            now=DEMO_NOW + timedelta(days=2),
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
        )
    except TokenRejected as exc:
        print("    the worker opens the same link two days later:", file=out)
        print(f"      REFUSED -- {exc.message}", file=out)

    _rule(out, "7. Replaying the confirmation changes nothing")
    replay = acknowledge_parchi(
        payload=payload,
        actor_worker_id=subject.parchi.worker_id,
        now=DEMO_NOW,
        store=store,
        tokens=tokens,
        ledger=ledger,
        audit=audit,
    )
    acks = audit.for_event(EVENT_TYPE_PARCHI_ACKNOWLEDGED)
    print(f"    this call reports already confirmed: {replay.already_confirmed}", file=out)
    print(f"    same event as before               : {replay.event.event_id}", file=out)
    print(
        f"    acknowledgement events written     : {len(acks)} (1 acknowledgement event -- "
        f"a double tap is one fact, not two)",
        file=out,
    )

    _rule(out, "8. Sealing the record")
    sealed = seal_parchi(
        parchi=store.get(subject.parchi.parchi_id),
        now=DEMO_NOW + timedelta(minutes=5),
        store=store,
        audit=audit,
    )
    print(f"    state          : {sealed.state.value}", file=out)
    print(f"    sealed at      : {sealed.sealed_at.isoformat()}", file=out)
    print(f"    content hash   : {sealed.content_hash}", file=out)
    print(f"    (sha-256 over the evidentiary fields, schema {sealed.schema_version})", file=out)
    print(f"    source documents: {', '.join(sealed.source_document_ids)}", file=out)
    for digest in sealed.source_hashes:
        print(f"    source sha-256 : {digest}", file=out)
    print(
        "\n    SEALED is terminal. There is no edit, update or amend operation anywhere in\n"
        "    this codebase: a correction would be a new record, never a mutation of this one.",
        file=out,
    )

    _rule(out, "9. The audit trail")
    for record in audit.records:
        interesting = {
            k: v
            for k, v in record.detail.items()
            if k in ("event_id", "parchi_id", "worker_id", "token_reference", "content_hash")
        }
        print(f"    {record.event}: {interesting}", file=out)

    raw = payload[len(TOKEN_SCHEME) :]
    print("", file=out)
    print(
        f"    the raw token IS in the audit trail: {raw in audit.all_text()}  <- must be False",
        file=out,
    )
    print(
        "    the raw token is never stored, anywhere, at any point: only its sha-256 and a\n"
        "    16-character reference derived from that hash are. A stolen database yields no\n"
        "    usable links.",
        file=out,
    )
    print(f"    seal events written: {len(audit.for_event(EVENT_TYPE_PARCHI_SEALED))}", file=out)

    print("", file=out)
    print(
        "DEMO COMPLETE. Nothing above invoked CAQM, and nothing above computed an amount.",
        file=out,
    )
    return ParchiExit.OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aadesh-parchi",
        description=(
            "Demonstrate the worker parchi acknowledgement flow end to end. "
            "Replays the corpus's revoked invocation; never claims a live one."
        ),
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args(argv)

    try:
        return int(run_demo(corpus_root=args.corpus))
    except AadeshError as exc:
        print(f"FAILED -- {exc}", file=sys.stderr)
        return int(ParchiExit.FAILED)


if __name__ == "__main__":
    raise SystemExit(main())
