"""INVARIANT: the demo shows the whole flow, and it never pretends GRAP is in force.

The single most dangerous thing this CLI could do is make a reviewer believe CAQM has invoked
a stage right now. The shipped corpus records exactly one invocation, and it was REVOKED in
January. So the demo has to walk a line: show a realistic end-to-end confirmation, while
saying on every screen that the stage it is replaying is history.

These tests are therefore as much about the OUTPUT as about the exit code.
"""

from __future__ import annotations

import io
import json

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_cli.parchi import ParchiExit, run_demo
from aadesh_web.server import Demo

CORPUS = "corpus"


@pytest.fixture
def output() -> io.StringIO:
    return io.StringIO()


def demo(output, **over):
    return run_demo(corpus_root=CORPUS, stream=output, **over)


# -------------------------------------------------------------------- demo CLI tests


def test_the_demo_runs_end_to_end(output):
    assert demo(output) is ParchiExit.OK


def test_the_demo_says_no_stage_is_currently_in_force(output):
    """The corpus's only invocation was revoked. The demo must not paper over that."""
    demo(output)
    text = output.getvalue().lower()

    assert "not currently in force" in text or "no stage is currently in force" in text


def test_the_demo_labels_the_stage_it_uses_as_a_historical_replay(output):
    demo(output)
    text = output.getvalue().lower()

    assert "historical" in text
    assert "replay" in text
    assert "revoked" in text


def test_the_demo_does_not_claim_a_live_caqm_invocation(output):
    demo(output)
    text = output.getvalue().lower()

    for claim in ("currently invoked", "stage iii is in force", "live invocation"):
        assert claim not in text


def test_the_demo_shows_the_worker_a_qr_they_could_actually_scan(output):
    demo(output)
    text = output.getvalue()

    assert "aadesh://ack/" in text


def test_the_demo_proves_the_qr_carries_no_worker_detail(output):
    demo(output)
    text = output.getvalue()

    payload = (
        next(line.strip() for line in text.splitlines() if "aadesh://ack/" in line)
        .split("aadesh://ack/")[1]
        .strip()
    )
    assert "worker-" not in payload
    assert "site-" not in payload
    assert "parchi-" not in payload


def test_the_demo_shows_the_sealed_content_hash(output):
    demo(output)
    text = output.getvalue()

    assert "content hash" in text.lower()
    assert "sha-256" in text.lower() or "sha256" in text.lower()


def test_the_demo_shows_the_audit_trail_it_wrote(output):
    demo(output)
    text = output.getvalue()

    assert "ParchiAcknowledged" in text
    assert "ParchiSealed" in text


def test_worker_view_exposes_only_the_verified_citations_attached_to_its_parchi():
    application = Demo(corpus_root=CORPUS)
    application.create_standing_order(scenario="replay")
    qr = application.roster_qr(scenario="replay")
    payload = next(item["payload"] for item in qr["workers"] if item["payload"])

    view = application.worker_view(payload)
    obligations = {item.obligation_id: item for item in LocalFileCorpus(CORPUS).obligations()}

    assert view["citations"]
    assert {item["obligation_id"] for item in view["citations"]} <= set(view["obligation_ids"])
    for citation in view["citations"]:
        expected = obligations[citation["obligation_id"]].citation
        assert citation["source_quote"] == expected.quote
        assert citation["source_page"] == expected.page
        assert citation["source_hash"] == expected.source_hash
        assert citation["source_url"].startswith("https://caqm.nic.in/")


def test_opening_the_roster_does_not_issue_parchis_or_mint_tokens():
    application = Demo(corpus_root=CORPUS)

    roster = application.roster_qr(scenario="replay")

    assert len(roster["workers"]) == 34
    assert roster["qr_minted"] == 0
    assert all(worker["payload"] is None for worker in roster["workers"])
    assert application.impact()["documented"] == 0


def test_the_demo_shows_that_a_replay_writes_no_second_acknowledgement(output):
    demo(output)
    text = output.getvalue()

    assert "already" in text.lower()
    assert "1 acknowledgement event" in text.lower() or "one acknowledgement event" in text.lower()


def test_the_demo_shows_a_colleague_being_refused(output):
    demo(output)
    text = output.getvalue().lower()

    assert "refused" in text
    assert "worker named on it" in text or "only the worker" in text


def test_the_demo_shows_the_raw_token_absent_from_the_audit_trail(output):
    """The claim the privacy tests make, demonstrated rather than asserted."""
    demo(output)
    text = output.getvalue().lower()

    assert "raw token" in text
    assert "not present" in text or "absent" in text or "never stored" in text


def test_the_demo_exits_non_zero_when_there_is_no_invocation_to_replay(tmp_path, output):
    (tmp_path / "invoked_stage.json").write_text("{}", encoding="utf-8")

    code = run_demo(corpus_root=tmp_path, stream=output)

    assert code is ParchiExit.NOTHING_TO_REPLAY
    assert "nothing to replay" in output.getvalue().lower()


def test_the_demo_output_is_stable_across_runs(output):
    """Same fixed clock, same records, same numbers -- only the tokens differ."""
    demo(output)
    first = output.getvalue()

    second_stream = io.StringIO()
    demo(second_stream)
    second = second_stream.getvalue()

    assert len(first) == len(second)


# -------------------------------------------------------------------- public impact


@pytest.fixture
def public_demo() -> Demo:
    return Demo(corpus_root=CORPUS)


def _public(demo: Demo) -> dict:
    return demo.public_impact()


def test_public_impact_exists_and_is_serializable(public_demo):
    payload = _public(public_demo)
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {
        "mode",
        "is_replay",
        "is_current_invocation",
        "invocation",
        "reading",
        "metrics",
        "data_note",
        "claim_boundary",
    }
    json.dumps(payload)  # must be JSON-serialisable


def test_public_impact_labels_itself_as_a_replay(public_demo):
    payload = _public(public_demo)
    assert payload["mode"] == "REPLAY"
    assert payload["is_replay"] is True
    assert payload["is_current_invocation"] is False


def test_public_impact_shows_the_revoked_stage_as_not_current(public_demo):
    payload = _public(public_demo)
    inv = payload["invocation"]
    assert inv is not None
    assert inv["stage"] == 3
    assert inv["lifecycle"] == "revoked"
    assert inv["is_current"] is False
    assert "revoked" in inv["describe"].lower()
    assert "not currently in force" in inv["describe"].lower()


def test_public_impact_labels_the_reading_as_synthetic(public_demo):
    payload = _public(public_demo)
    reading = payload["reading"]
    assert reading is not None
    assert reading["is_synthetic"] is True
    assert reading["is_measured"] is False
    assert reading["provenance"] == "synthetic"


def test_public_impact_metric_counters_are_derived_not_invented(public_demo):
    """Every count must be traceable to an actual underlying record."""
    payload = _public(public_demo)
    m = payload["metrics"]

    # 1. Standing Orders: the demo starts with none created.
    assert m["sites_with_active_standing_orders"]["count"] == 0
    assert m["sites_with_active_standing_orders"]["status"] == "unavailable"

    # 2. Sites acknowledging regulated halts: the replay stage is invoked AND
    #    the demo piling site's activity_type is a restricted activity, so the
    #    site-level acknowledgement is demonstrable.
    assert m["sites_acknowledging_regulated_halts"]["count"] == 1
    assert m["sites_acknowledging_regulated_halts"]["status"] == "demo"

    # 3. Dust-generating activities halted: count of applicable
    #    issues_parchi obligations. NOT a per-worker count, NOT doubled by
    #    multiple parchis.
    assert m["dust_activities_halted"]["count"] >= 1
    assert m["dust_activities_halted"]["status"] == "demo"

    # 4. Workers with documented displacement: Parchis issued. Before a
    #    Standing Order is created, this is zero.
    assert m["workers_with_documented_displacement"]["count"] == 0
    assert m["workers_with_documented_displacement"]["status"] == "unavailable"


def test_public_impact_does_not_double_count_activities(public_demo):
    """Creating parchis for 34 workers must NOT inflate the dust-activities count."""
    m_before = _public(public_demo)["metrics"]
    public_demo.create_standing_order(scenario="replay")
    m_after = _public(public_demo)["metrics"]

    # dust_activities_halted is an obligation-category count, not a parchi count
    assert m_after["dust_activities_halted"]["count"] == m_before["dust_activities_halted"]["count"]

    # workers_with_documented_displacement reflects parchis, so it goes up
    assert (
        m_after["workers_with_documented_displacement"]["count"]
        > m_before["workers_with_documented_displacement"]["count"]
    )


def test_public_impact_standing_order_count_goes_up_after_creation(public_demo):
    _public(public_demo)["metrics"]["sites_with_active_standing_orders"]["count"]
    public_demo.create_standing_order(scenario="replay")
    after = _public(public_demo)["metrics"]["sites_with_active_standing_orders"]
    assert after["count"] == 1
    assert after["status"] == "demo"
    assert after["reporting_period"] is not None


def test_public_impact_does_not_expose_worker_pii(public_demo):
    """The public payload must contain no worker name, id, qr token, or parchi id."""
    public_demo.create_standing_order(scenario="replay")
    payload_text = json.dumps(_public(public_demo), ensure_ascii=False)

    banned = (
        "worker-001",
        "worker-034",
        "display_name",
        "Worker 001",
        "Worker 034",
        "aadesh://ack/",
    )
    for token in banned:
        assert token not in payload_text, (
            f"Public impact payload contained {token!r}; the public endpoint must"
            " not expose worker ids, names, or qr tokens."
        )


def test_public_impact_does_not_expose_parchi_ids(public_demo):
    public_demo.create_standing_order(scenario="replay")
    payload_text = json.dumps(_public(public_demo), ensure_ascii=False)

    # Parchi ids exist after creation; they must not leak.
    assert "parchi:" not in payload_text


def test_public_impact_does_not_claim_a_measured_environmental_improvement(public_demo):
    """The claim_boundary sentence must NOT affirmatively claim environmental improvement.

    The claim_boundary is allowed to MENTION these concepts in order to deny them
    (e.g. "does not estimate tonnes of emissions avoided"). What it must not do is
    ASSERT them positively.
    """
    payload = _public(public_demo)
    boundary = payload["claim_boundary"].lower()

    # The boundary must contain the explicit disclaimer.
    assert "does not independently establish" in boundary
    assert "does not" in boundary

    # It must not positively claim improvement. Avoid false positives on the
    # denial form "does not estimate X" by checking the affirmative forms.
    for forbidden in (
        "reduced pm2.5 by",
        "improved aqi by",
        "reduced aqi by",
        "avoided " + "tonnes",
        " tonnes of emissions were",
        "emissions were avoided",
    ):
        assert forbidden not in boundary, (
            f"Public impact claim_boundary contained the affirmative phrase {forbidden!r}."
        )

    # The presence of "tonnes of emissions avoided" in a DENIAL form is fine;
    # check that it appears only as part of a denial.
    if "tonnes of emissions avoided" in boundary:
        assert "does not" in boundary and "estimate" in boundary


def test_public_impact_data_note_does_not_present_replay_as_current(public_demo):
    payload = _public(public_demo)
    note = payload["data_note"].lower()

    assert "historical" in note or "replay" in note or "demonstration" in note
    assert "no verified current invocation" in note or "no verified current" in note


def test_public_impact_metric_status_reasons_distinguish_demo_from_measured(public_demo):
    m = _public(public_demo)["metrics"]
    for key in (
        "sites_with_active_standing_orders",
        "sites_acknowledging_regulated_halts",
        "dust_activities_halted",
        "workers_with_documented_displacement",
    ):
        metric = m[key]
        assert metric["status"] in {"live", "demo", "synthetic", "historical", "unavailable"}
        assert metric["status_reason"]
        assert metric["count"] >= 0


def test_public_impact_unavailable_state_when_no_invocation(shipped_corpus, tmp_path):
    """With no verified invocation at all, every metric should degrade honestly.

    We build a corpus that has the shipped sources (so it can be verified) but
    NO invocations -- proving that the public impact endpoint degrades to an
    honest empty state rather than inventing a stage.

    The public_impact() method defaults to the replay scenario, which requires
    a matching historical invocation. We call it with the current scenario
    explicitly so we can test the 'no invocation at all' path.
    """
    from aadesh_adapters.corpus.local_file import LocalFileCorpus

    # Copy the shipped sources into the tmp path so the snapshot can be proved.
    sources_dir = shipped_corpus / "sources"
    if sources_dir.exists():
        import shutil

        shutil.copytree(sources_dir, tmp_path / "sources")
    for marker in ("manifest.json", "sources/manifest.json"):
        src = shipped_corpus / marker
        if src.exists():
            import shutil

            shutil.copy2(src, tmp_path / marker)

    corpus = LocalFileCorpus(tmp_path).snapshot()
    assert len(corpus.invocations) == 0

    demo = Demo(corpus_root=tmp_path)
    # Use current scenario to test the no-invocation path
    payload = demo.public_impact(current_scenario=True)
    assert payload["invocation"] is None
    assert payload["is_current_invocation"] is False

    m = payload["metrics"]
    assert m["sites_acknowledging_regulated_halts"]["count"] == 0
    assert m["dust_activities_halted"]["count"] == 0


def test_public_impact_behaves_the_same_after_acknowledgement(public_demo):
    """Acknowledging workers changes parchi state, not the public aggregate shape."""
    public_demo.create_standing_order(scenario="replay")
    before = _public(public_demo)["metrics"]["workers_with_documented_displacement"]["count"]

    roster = public_demo.roster_qr(scenario="replay")
    worker = next(w for w in roster["workers"] if w["worker_id"] == "worker-001")
    assert worker["payload"] is not None
    public_demo.acknowledge(worker["payload"], "worker-001")

    after = _public(public_demo)["metrics"]["workers_with_documented_displacement"]["count"]
    assert after == before  # documented displacement count is parchi count, unchanged by ack


def test_public_impact_has_a_honest_empty_state_before_any_order(public_demo):
    """Before a Standing Order exists, the affected metrics reflect that honestly."""
    m = _public(public_demo)["metrics"]
    assert m["sites_with_active_standing_orders"]["count"] == 0
    assert m["sites_with_active_standing_orders"]["status"] == "unavailable"
    assert m["workers_with_documented_displacement"]["count"] == 0
    assert m["workers_with_documented_displacement"]["status"] == "unavailable"
