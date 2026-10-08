"""INVARIANT: the demo shows the whole flow, and it never pretends GRAP is in force.

The single most dangerous thing this CLI could do is make a reviewer believe CAQM has invoked
a stage right now. The shipped corpus records exactly one invocation, and it was REVOKED in
January. So the demo has to walk a line: show a realistic end-to-end confirmation, while
saying on every screen that the stage it is replaying is history.

These tests are therefore as much about the OUTPUT as about the exit code.
"""

from __future__ import annotations

import io

import pytest

from aadesh_cli.parchi import ParchiExit, run_demo

CORPUS = "corpus"


@pytest.fixture
def output() -> io.StringIO:
    return io.StringIO()


def demo(output, **over):
    return run_demo(corpus_root=CORPUS, stream=output, **over)


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
