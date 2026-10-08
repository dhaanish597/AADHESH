"""LEGAL ACTIVATION BOUNDARY — an AQI reading can never turn itself into an enforcement order.

Aadesh's central legal claim is that there are two different things and they are never merged:

  * the **implied** stage, derived from a cited AQI band and a reading; and
  * the **invoked** stage, which exists only because a CAQM order says so.

Only the invoked stage activates a clause. This file proves the boundary from both sides: the
implied stage really is computed (it is not just switched off), and it still activates nothing.

The four cases below are the ones the verification brief names. Three of them use a synthetic
test corpus built under tmp_path (a test order is not a CAQM order, and saying otherwise would
be the exact dishonesty this package exists to prevent). Case D uses the REAL recorded
16.01.2026 invocation and 22.01.2026 revocation in `corpus/`, because that is the only piece of
this that actually happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain import ReplayContext
from aadesh_core.domain.enums import ObligationStatus, ResolutionMode, StageAgreement
from aadesh_core.resolver import resolve_obligations
from aadesh_core.stages import derive_implied_stage
from tests.verification.harness import NOW, OBLIGATION_ID, build_corpus, reading, site

REPLAY_FIXTURE = "fixtures/replays/january-2026-stage-iii.json"


def _resolve(corpus: Path, *, value: float = 420.0, replay: ReplayContext | None = None):
    return resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=NOW,
        reading=reading(value),
        replay=replay,
    )


# --- the implied stage is real, and the reading is only a reading ------------


def test_the_implied_stage_is_actually_derived_from_a_cited_band(tmp_path: Path) -> None:
    """Guard against the cheap way to pass the tests below: never computing the implied stage
    at all. This asserts the AQI reading really does imply Stage III here."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(2, 3))
    bands = LocalFileCorpus(corpus).stage_bands()

    implied = derive_implied_stage(reading=reading(420.0), bands=bands)

    assert implied.stage == 3
    assert implied.citation is not None
    assert implied.citation.source_doc == "test-grap-order"


def test_only_band_comparison_is_used_so_a_boundary_value_does_not_leak(tmp_path: Path) -> None:
    """401-450 is Stage III and 301-400 is Stage II. The bands are compared, not subtracted: a
    value one below the boundary must fall in the lower band, not round up."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(2, 3))
    bands = LocalFileCorpus(corpus).stage_bands()

    assert derive_implied_stage(reading=reading(400.0), bands=bands).stage == 2
    assert derive_implied_stage(reading=reading(401.0), bands=bands).stage == 3


# --- CASE A: AQI implies Stage III, no official invocation -------------------


def test_case_a_an_implied_stage_with_no_official_invocation_activates_nothing(
    shipped_corpus: Path,
) -> None:
    """The shipped corpus has a REVOKED invocation and therefore no live stage. An AQI of 420
    implies Stage III. Nothing is activated, because nothing was invoked."""
    corpus = LocalFileCorpus(shipped_corpus)
    assert corpus.invoked_stage() is None, (
        "the shipped corpus must not carry a live invocation; if this fails, stop and check "
        "whether someone forged current CAQM data"
    )

    result = _resolve(shipped_corpus, value=420.0)

    assert result.stage_status.implied_stage == 3, "the reading really does imply Stage III"
    assert result.stage is None
    # The reading and the orders disagree -- the reading asserts a stage no order invoked. That
    # is a discrepancy against an absent official stage, and reporting it as one is the point:
    # the gap is surfaced rather than either ignored or silently acted upon.
    assert result.stage_status.status is StageAgreement.DISCREPANCY
    assert result.applicable == ()
    assert all(r.status is ObligationStatus.NOT_APPLICABLE for r in result.results)
    assert all("No verified current official CAQM stage" in r.reason for r in result.results)


@pytest.mark.parametrize("value", [500.0, 99999.0, 450.5])
def test_case_a_an_extreme_reading_still_cannot_invoke_a_stage(
    shipped_corpus: Path, value: float
) -> None:
    """Scaling the number up is the crudest attack on the boundary. It changes the implied
    stage at most; the official stage stays None."""
    result = _resolve(shipped_corpus, value=value)
    assert result.stage is None
    assert result.applicable == ()


# --- CASE B: AQI implies Stage III, but the order invoked Stage II -----------


def test_case_b_a_discrepancy_is_reported_and_the_higher_stage_is_not_activated(
    tmp_path: Path,
) -> None:
    """The reading says Stage III; the order says Stage II. The interesting failure would be
    silently taking the higher of the two, which would invent an enforcement action from a
    sensor. The official stage stays authoritative and the discrepancy is visible."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=2, bands=(2, 3))

    result = _resolve(corpus, value=420.0)

    assert result.stage is not None and result.stage.stage == 2
    assert result.stage_status.implied_stage == 3
    assert result.stage_status.status is StageAgreement.DISCREPANCY
    assert result.stage_status.divergent is True
    assert result.applicable == ()
    assert all(r.status is ObligationStatus.NOT_APPLICABLE for r in result.results)


# --- CASE C: official Stage III, the reading says otherwise ------------------


def test_case_c_the_official_stage_remains_authoritative_when_the_reading_agrees_with_nothing(
    tmp_path: Path,
) -> None:
    """A clean reading that falls in no band leaves the implied stage undeterminable. The
    order still governs: clauses at Stage III are evaluated on their facts."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))

    result = _resolve(corpus, value=100.0)

    assert result.stage_status.implied_stage is None
    assert result.stage_status.status is StageAgreement.OFFICIAL_ONLY
    assert result.stage is not None and result.stage.stage == 3
    assert [r.obligation_id for r in result.applicable] == [OBLIGATION_ID]
    assert result.results[0].status is ObligationStatus.MET


def test_case_c_a_reading_for_a_different_pollutant_cannot_imply_a_stage(tmp_path: Path) -> None:
    """PM2.5 is not AQI. A concentration in the AQI band's numeric range must not be compared
    against the AQI band."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))

    result = resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=NOW,
        reading=reading(420.0, parameter="PM2.5"),
    )

    assert result.stage_status.implied_stage is None
    assert result.stage is not None and result.stage.stage == 3


# --- CASE D: historical invocation -- replay only ----------------------------


def test_case_d_the_real_january_invocation_replays_but_is_never_current(
    shipped_corpus: Path, repo_root: Path
) -> None:
    """The recorded 16.01.2026 Stage III invocation, replayed against the recorded 22.01.2026
    revocation. It must be usable as history and unusable as law."""
    replay = json.loads((repo_root / REPLAY_FIXTURE).read_text(encoding="utf-8"))
    context = ReplayContext(
        invocation_date=replay["invocation_date"], revocation_date=replay["revocation_date"]
    )

    result = _resolve(shipped_corpus, value=420.0, replay=context)

    assert result.mode is ResolutionMode.REPLAY
    assert result.stage is not None and result.stage.stage == 3
    assert result.stage.is_current is False, "replay must not relabel history as current"
    assert result.current_stage is None, "there is no live invocation to report"
    assert result.replay_notice is not None
    assert "not a current invocation" in result.replay_notice


def test_case_d_a_replay_does_not_change_what_current_mode_reports(shipped_corpus: Path) -> None:
    """Running a replay must not move the live state. Resolving again in CURRENT mode at the
    same instant still reports no invocation."""
    before = _resolve(shipped_corpus, value=420.0)
    _resolve(
        shipped_corpus,
        value=420.0,
        replay=ReplayContext(invocation_date="2026-01-16", revocation_date="2026-01-22"),
    )
    after = _resolve(shipped_corpus, value=420.0)

    assert before.mode is after.mode is ResolutionMode.CURRENT
    assert before.stage is None and after.stage is None
    assert [r.status for r in before.results] == [r.status for r in after.results]


def test_case_d_current_mode_hides_a_revoked_invocation_even_at_a_historical_instant(
    shipped_corpus: Path,
) -> None:
    """Choosing a `now` inside the invocation's original window does not resurrect it. Only an
    explicit ReplayContext does, and then only in REPLAY mode."""
    historical = NOW.replace(year=2026, month=1, day=18)
    result = resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(shipped_corpus).snapshot(),
        now=historical,
        reading=reading(420.0),
    )

    assert result.mode is ResolutionMode.CURRENT
    assert result.stage is None
    assert result.applicable == ()
