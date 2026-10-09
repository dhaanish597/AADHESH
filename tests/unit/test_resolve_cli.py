"""The local interface uses real corpus verification and cannot accept a fabricated stage."""

from __future__ import annotations

import json
import shutil

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_cli.resolve import main

NOW = "2026-10-08T09:00:00+00:00"


def arguments(repo_root):
    return [
        "--site",
        str(repo_root / "fixtures/sites/piling-site.json"),
        "--corpus",
        str(repo_root / "corpus"),
        "--now",
        NOW,
    ]


def test_cli_current_mode_has_no_activated_obligations(repo_root, capsys):
    assert main(arguments(repo_root)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "CURRENT"
    assert result["official_stage"] == "NONE"
    assert result["summary"]["applicable"] == 0
    assert all(row["status"] == "NOT_APPLICABLE" for row in result["obligations"])


def test_cli_replay_is_explicit_and_does_not_change_current_invocation(repo_root, capsys):
    path = repo_root / "corpus/invoked_stage.json"
    before = path.read_bytes()
    args = [
        *arguments(repo_root),
        "--replay",
        str(repo_root / "fixtures/replays/january-2026-stage-iii.json"),
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "REPLAY"
    assert result["official_stage"] == 3
    assert result["current_official_stage"] == "NONE"
    assert all(
        row["mode"] == "REPLAY" and "Historical scenario replay" in row["reason"]
        for row in result["obligations"]
    )
    assert path.read_bytes() == before
    assert LocalFileCorpus(repo_root / "corpus").invoked_stage() is None


def test_cli_cannot_treat_an_observation_as_an_invocation(repo_root, capsys):
    args = [
        *arguments(repo_root),
        "--observation",
        str(repo_root / "fixtures/observations/aqi-discrepancy.json"),
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["official_stage"] == "NONE"
    assert result["implied_stage"] == 3
    assert result["stage_status"] == "DISCREPANCY"
    assert result["reading"]["provenance"] == "synthetic"
    assert result["summary"]["applicable"] == 0


def test_cli_refuses_a_bare_stage_override(repo_root, capsys):
    with pytest.raises(SystemExit) as error:
        main([*arguments(repo_root), "--stage", "3"])
    assert error.value.code != 0
    assert "unrecognized arguments" in capsys.readouterr().err


def test_cli_propagates_full_citations(repo_root, capsys):
    assert (
        main(
            [
                *arguments(repo_root),
                "--replay",
                str(repo_root / "fixtures/replays/january-2026-stage-iii.json"),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    for row in result["obligations"]:
        assert row["source_doc"] and row["source_page"] > 0 and row["source_quote"]
        assert len(row["source_hash"]) == 64
        assert row["evidence"]
        for evidence in row["evidence"]:
            assert evidence["source_quote"] and len(evidence["source_hash"]) == 64


def test_cli_tampered_source_returns_an_error_without_actions(repo_root, tmp_path, capsys):
    root = tmp_path / "corpus"
    shutil.copytree(repo_root / "corpus", root, ignore=shutil.ignore_patterns("incoming_sources"))
    pdf = root / "sources/caqm-grap-schedule-2026-09-29.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"tampered")
    args = ["--site", str(repo_root / "fixtures/sites/piling-site.json"), "--corpus", str(root)]
    assert main(args) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"] == "CORPUS_INTEGRITY"


@pytest.mark.parametrize(
    "extra", [{"active_workers": 500}, {"in_ncr": "yes"}, {"plot_size_sqm": True}]
)
def test_cli_rejects_invalid_site_inputs(repo_root, tmp_path, capsys, extra):
    path = tmp_path / "site.json"
    path.write_text(json.dumps({"site_id": "site", **extra}))
    args = arguments(repo_root)
    args[1] = str(path)
    assert main(args) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"] == "INVALID_INPUT"


@pytest.mark.parametrize("value", [True, "420", float("nan"), float("inf")])
def test_cli_rejects_invalid_observations_without_a_traceback(repo_root, tmp_path, capsys, value):
    observation = json.loads((repo_root / "fixtures/observations/aqi-discrepancy.json").read_text())
    observation["value"] = value
    path = tmp_path / "observation.json"
    path.write_text(json.dumps(observation))
    assert main([*arguments(repo_root), "--observation", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"] == "INVALID_INPUT"


def test_cli_replay_cannot_request_an_unrecorded_order(repo_root, tmp_path, capsys):
    path = tmp_path / "replay.json"
    path.write_text(json.dumps({"invocation_date": "2026-01-17", "revocation_date": "2026-01-22"}))
    assert main([*arguments(repo_root), "--replay", str(path)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"] == "CORPUS_INTEGRITY"


def test_cli_is_reproducible_with_an_explicit_time(repo_root, capsys):
    assert main(arguments(repo_root)) == 0
    first = capsys.readouterr().out
    assert main(arguments(repo_root)) == 0
    assert capsys.readouterr().out == first
