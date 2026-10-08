"""HISTORICAL REPLAY — January's order is history, and history is not law.

The one invocation in this repository that actually happened is the real CAQM Stage III order
of 16.01.2026, revoked on 22.01.2026. It is kept in `corpus/` as evidence about the past.

This file uses it for both halves of the claim. The replay must be *usable*: it drives the real
resolver and produces the real Stage III obligations, which is what makes it worth keeping. And
it must be *inert*: it can never appear as a current invocation, never fire a standing order,
and never move the live state.

Every test here is labelled a historical replay, on purpose. If a future reader finds one of
these assertions in isolation, the dates should tell them what they are looking at.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain import ReplayContext
from aadesh_core.domain.enums import (
    InvocationLifecycle,
    ResolutionMode,
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
)
from aadesh_core.resolver import resolve_obligations
from aadesh_core.standing_order import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    activate,
    confirm,
    fire,
)
from aadesh_core.standing_order.trigger import StageTripEvent, evaluate_trigger
from tests.verification.harness import NOW, VALID_FROM, VALID_UNTIL, reading, site, stack

REPLAY_FIXTURE = "fixtures/replays/january-2026-stage-iii.json"
HISTORICAL_DOC = "caqm-grap-stage3-order-2026-01-16"
REVOCATION_DOC = "caqm-grap-stage3-revocation-2026-01-22"

#: The real dates, written out rather than read from the fixture, so a changed fixture is a
#: failing test rather than a silently different scenario.
INVOKED_ON = "2026-01-16"
REVOKED_ON = "2026-01-22"

#: An instant inside the order's effective window. Deliberately a HISTORICAL replay: this is
#: a time at which the order was in force, which is precisely when the temptation to treat it
#: as current is strongest.
WITHIN_WINDOW = datetime(2026, 1, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def replay_context(repo_root: Path) -> ReplayContext:
    payload = json.loads((repo_root / REPLAY_FIXTURE).read_text(encoding="utf-8"))
    assert payload["invocation_date"] == INVOKED_ON
    assert payload["revocation_date"] == REVOKED_ON
    return ReplayContext(
        invocation_date=payload["invocation_date"], revocation_date=payload["revocation_date"]
    )


def _resolve(corpus: Path, *, now: datetime = NOW, replay: ReplayContext | None = None):
    return resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=now,
        reading=reading(420.0),
        replay=replay,
    )


# --- the history is real, not a scenario -------------------------------------


def test_the_replay_is_the_recorded_invocation_not_a_fabricated_one(shipped_corpus: Path) -> None:
    """Guard: this whole file is worthless if the replay is pointed at invented data. The
    historical invocation must be the real revoked one, cited to the real order, with its
    revocation cited to the real revocation order."""
    corpus = LocalFileCorpus(shipped_corpus)
    historical = [
        invocation
        for invocation in corpus.invocation_history()
        if invocation.lifecycle is InvocationLifecycle.REVOKED
    ]

    assert len(historical) == 1, "expected exactly one historical invocation on record"
    invocation = historical[0]
    assert invocation.stage == 3
    assert invocation.order_doc_id == HISTORICAL_DOC
    assert invocation.invoked_at.date().isoformat() == INVOKED_ON
    assert invocation.revoked_at is not None
    assert invocation.revoked_at.date().isoformat() == REVOKED_ON
    assert invocation.revocation_citation is not None
    assert invocation.revocation_citation.source_doc == REVOCATION_DOC
    assert invocation.is_current is False


# --- the replay is usable -----------------------------------------------------


def test_the_historical_replay_drives_the_real_resolver(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    """A replay that could not exercise the deterministic core would be a decorative fixture.
    This one resolves to the historically invoked stage and evaluates the corpus's clauses."""
    result = _resolve(shipped_corpus, replay=replay_context)

    assert result.mode is ResolutionMode.REPLAY
    assert result.stage is not None
    assert result.stage.stage == 3
    assert result.results, "the replay must actually evaluate the corpus's obligations"
    assert result.excluded_unsourced == (), "the shipped corpus is fully sourced"


def test_the_replayed_stage_still_carries_the_bytes_it_came_from(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    """Historical does not mean unattributed. The replayed stage names its order and the hash of
    the document, exactly as a current one would."""
    result = _resolve(shipped_corpus, replay=replay_context)

    assert result.stage is not None
    assert result.stage.order_doc_id == HISTORICAL_DOC
    assert result.stage.order_sha256
    assert result.stage.citation is not None
    assert result.stage.citation.source_doc == HISTORICAL_DOC


def test_a_replay_instant_outside_the_effective_window_is_refused(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    """The replay is bounded by the order's own lifetime. Asking for an instant before it was
    issued, or after it was revoked, is not a replay of anything."""
    from aadesh_core.errors import CorpusIntegrityError

    with pytest.raises(CorpusIntegrityError):
        resolve_obligations(
            site=site(),
            corpus=LocalFileCorpus(shipped_corpus).snapshot(),
            now=NOW,
            reading=reading(420.0),
            replay=ReplayContext(
                invocation_date=INVOKED_ON,
                revocation_date=REVOKED_ON,
                at=WITHIN_WINDOW.replace(year=2027),
            ),
        )


# --- the replay is inert ------------------------------------------------------


def test_a_replayed_stage_is_never_relabelled_current(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    result = _resolve(shipped_corpus, replay=replay_context)

    assert result.stage is not None
    assert result.stage.is_current is False
    assert result.stage.lifecycle is InvocationLifecycle.REVOKED
    assert result.current_stage is None


def test_the_replay_notice_says_out_loud_that_it_is_not_current(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    result = _resolve(shipped_corpus, replay=replay_context)

    assert result.replay_notice is not None
    assert "not a current invocation" in result.replay_notice


def test_the_replayed_stage_cannot_fire_a_standing_order(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    """The tightest statement of the boundary, closed into a loop: take the stage the replay
    just produced and offer it to the trigger. The order is otherwise perfect -- right site,
    right stage, signed, live window -- and it still does not fire."""
    replayed = _resolve(shipped_corpus, replay=replay_context).stage
    assert replayed is not None

    order = StandingOrder(
        standing_order_id="so-1",
        site_id="site-001",
        supervisor_id="sup-1",
        trigger=StageInvocationTrigger(stage=3, match=StageMatch.EXACT),
        actions=(StandingOrderActionClause(action=StandingOrderAction.ISSUE_HALT),),
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        status=StandingOrderStatus.DRAFT,
        created_at=VALID_FROM,
    )
    order = fire(
        activate(confirm(order, supervisor_id="sup-1", now=VALID_FROM), now=VALID_FROM), now=NOW
    )

    decision = evaluate_trigger(
        order=order,
        event=StageTripEvent(invoked=replayed, site_id="site-001"),
        now=NOW,
    )

    assert decision.fires is False
    assert decision.refusal.code == "NOT_CURRENT_INVOCATION"


def test_current_mode_at_the_historical_instant_still_hides_the_order(
    shipped_corpus: Path,
) -> None:
    """The attack the replay machinery exists to prevent: rather than asking for a replay, just
    pass a `now` from January. The invocation was in force then -- and it is still not served,
    because currency is a property of the record, not of the clock the caller supplies."""
    result = _resolve(shipped_corpus, now=WITHIN_WINDOW)

    assert result.mode is ResolutionMode.CURRENT
    assert result.stage is None
    assert result.applicable == ()


# --- the replay does not move the live state ---------------------------------


def test_running_a_replay_does_not_alter_what_current_mode_reports(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    before = _resolve(shipped_corpus)
    _resolve(shipped_corpus, replay=replay_context)
    after = _resolve(shipped_corpus)

    assert before.mode is after.mode is ResolutionMode.CURRENT
    assert before.stage is None and after.stage is None
    assert [r.status for r in before.results] == [r.status for r in after.results]


def test_the_replay_writes_nothing_anywhere(
    shipped_corpus: Path, repo_root: Path, replay_context: ReplayContext
) -> None:
    """Replay is a read. It creates no parchi, consumes no token and leaves no audit record --
    so a replay can never be mistaken, later, for something the system did."""
    parts = stack(repo_root)

    _resolve(shipped_corpus, replay=replay_context)

    assert parts.audit.records == []
    assert parts.parchi_store.get("parchi:exec-1:wrk-1") is None


def test_the_shipped_corpus_is_byte_identical_after_replaying_it(
    shipped_corpus: Path, replay_context: ReplayContext
) -> None:
    """The strongest form of "does not alter current state": the bytes on disk are unchanged."""
    before = {p: p.read_bytes() for p in shipped_corpus.rglob("*") if p.is_file()}

    _resolve(shipped_corpus, replay=replay_context)

    after = {p: p.read_bytes() for p in shipped_corpus.rglob("*") if p.is_file()}
    assert before == after
