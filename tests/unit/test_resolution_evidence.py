"""Adversarial evidence and architecture checks for the deterministic resolution boundary."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.citations import quote_names_stage
from aadesh_core.domain import InvocationLifecycle, ObligationStatus, SourceState
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.resolver import resolution_to_dict, resolve_obligations
from aadesh_core.verification import CitationCheck, VerificationReport, verify_corpus
from tests.support.builders import FIXED_NOW, invoked_stage, obligation, reading, site, snapshot
from tests.support.resolution import construction_site, with_test_stage


@pytest.fixture
def scratch(tmp_path, shipped_corpus):
    destination = tmp_path / "corpus"
    shutil.copytree(shipped_corpus, destination, ignore=shutil.ignore_patterns("incoming_sources"))
    return destination


def edit_rule(root, rule_id, edit):
    path = root / "obligations/construction_site.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rule = next(rule for rule in payload["obligations"] if rule["obligation_id"] == rule_id)
    edit(rule)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_all_original_primary_citations_are_preserved(shipped_corpus, repo_root):
    baseline = json.loads(
        (repo_root / "tests/fixtures/resolution/primary-citations.json").read_text(encoding="utf-8")
    )
    current = json.loads(
        (shipped_corpus / "obligations/construction_site.json").read_text(encoding="utf-8")
    )
    actual = [
        {key: rule[key] for key in ("obligation_id", "source_doc", "page", "quote")}
        for rule in current["obligations"]
    ]
    assert actual == baseline


@pytest.mark.parametrize("field", ["source_doc", "page", "quote"])
def test_missing_primary_citation_cannot_be_replaced_by_good_supporting_evidence(scratch, field):
    edit_rule(scratch, "grap3-cd-piling", lambda rule: rule.pop(field))
    report = verify_corpus(scratch)
    assert report.has_failures
    assert "grap3-cd-piling" not in report.verified_entry_ids
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(scratch).snapshot()


def test_one_good_quote_cannot_launder_an_unproved_exception(scratch):
    def damage(rule):
        rule["evidence"]["categories"]["quote"] += " An invented additional condition."

    edit_rule(scratch, "grap3-cd-piling", damage)
    loader = LocalFileCorpus(scratch)
    rule = next(rule for rule in loader.obligations() if rule.obligation_id == "grap3-cd-piling")
    assert rule.source_state is SourceState.UNSOURCED
    assert "grap3-cd-piling" not in loader.verification_report().verified_entry_ids
    with pytest.raises(CorpusIntegrityError):
        loader.snapshot()


def test_deleted_condition_evidence_refuses_resolution(scratch):
    edit_rule(scratch, "grap3-cd-piling", lambda rule: rule["evidence"].pop("categories"))
    with pytest.raises(CorpusIntegrityError, match="evidence"):
        LocalFileCorpus(scratch).snapshot()


def test_an_uncited_numeric_rule_literal_is_refused(scratch):
    def damage(rule):
        rule["applicability"]["conditions"][1]["value"] = 501

    edit_rule(scratch, "grap1-cd-large-project-registration", damage)
    assert verify_corpus(scratch).has_failures
    with pytest.raises(CorpusIntegrityError, match="uncited legal literal"):
        LocalFileCorpus(scratch).snapshot()


def test_worker_count_cannot_be_encoded_as_an_uncited_legal_condition(scratch):
    def damage(rule):
        rule["applicability"]["conditions"][1]["field"] = "active_workers"

    edit_rule(scratch, "grap1-cd-large-project-registration", damage)
    with pytest.raises(CorpusIntegrityError, match="active_workers"):
        LocalFileCorpus(scratch).snapshot()


def test_tampering_after_a_previous_verification_is_not_hidden_by_a_cache(scratch):
    loader = LocalFileCorpus(scratch)
    assert not loader.verification_report().has_failures
    assert loader.snapshot().obligations
    path = scratch / "sources/caqm-grap-schedule-2026-09-29.pdf"
    content = bytearray(path.read_bytes())
    content[-1] ^= 1
    path.write_bytes(content)
    assert loader.verification_report().has_failures
    assert all(rule.source_state is SourceState.UNSOURCED for rule in loader.obligations())
    with pytest.raises(CorpusIntegrityError, match="hash"):
        loader.snapshot()


def test_a_forged_page_cache_cannot_prove_a_quote_with_an_untouched_pdf(scratch):
    path = scratch / "sources/pages/caqm-grap-schedule-2026-09-29/p2.txt"
    forged = "A fabricated new construction requirement."
    path.write_text(path.read_text(encoding="utf-8") + "\n" + forged, encoding="utf-8")
    edit_rule(scratch, "grap1-cd-dust-mitigation", lambda rule: rule.update(quote=forged))
    report = verify_corpus(scratch)
    assert report.documents_verified == 3  # The PDFs alone cannot prove the altered cache.
    assert any("extracted page 2 hash" in check.detail for check in report.citations_failed)
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(scratch).snapshot()


def test_a_missing_page_hash_cannot_be_treated_as_a_legacy_verified_cache(scratch):
    path = scratch / "sources/manifest.json"
    data = json.loads(path.read_text())
    data["documents"][0].pop("page_sha256")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CorpusIntegrityError, match="page hash"):
        LocalFileCorpus(scratch).snapshot()


@pytest.mark.parametrize("field,value", [("quote", ""), ("source_hash", None)])
def test_setting_verified_cannot_create_a_citation_or_hash(field, value):
    rule = obligation()
    rule = replace(rule, citation=replace(rule.citation, **{field: value}))
    result = resolve_obligations(
        site=site(), corpus=snapshot(obligations=[rule], stage=invoked_stage()), now=FIXED_NOW
    )
    assert result.results == ()
    assert len(result.excluded_unsourced) == 1
    assert not result.fully_sourced
    assert resolution_to_dict(result)["obligations"] == []


def test_verification_flag_without_proof_receipt_cannot_resolve():
    data = snapshot(obligations=[obligation()], stage=invoked_stage())
    data = replace(data, proved_citations=frozenset({data.invocations[0].citation}))
    result = resolve_obligations(site=site(), corpus=data, now=FIXED_NOW)
    assert not result.results
    assert result.excluded_unsourced


def test_official_invocation_requires_its_own_proof_receipt():
    data = snapshot(obligations=[obligation()], stage=invoked_stage())
    data = replace(data, proved_citations=data.proved_citations - {data.invocations[0].citation})
    with pytest.raises(CorpusIntegrityError, match="Official invocation"):
        resolve_obligations(site=site(), corpus=data, now=FIXED_NOW)


def test_verification_receipts_are_scoped_by_kind_and_require_every_citation(tmp_path):
    report = VerificationReport(
        tmp_path,
        citations=[
            CitationCheck("stage_band", "3", "doc", 1, True, "ok"),
            CitationCheck("invoked_stage", "3", "doc", 2, True, "ok"),
            CitationCheck("invoked_stage", "3", "doc", 3, False, "bad revocation"),
        ],
    )
    assert report.verified_entries == {("stage_band", "3")}


def test_relabelling_a_proved_historical_invocation_does_not_prove_current_activation(
    verified_corpus,
):
    historical = verified_corpus.invocations[0]
    forged = replace(
        historical, lifecycle=InvocationLifecycle.ACTIVE, revoked_at=None, revocation_citation=None
    )
    changed = replace(verified_corpus, invocations=(forged,))
    with pytest.raises(CorpusIntegrityError, match="Official invocation"):
        resolve_obligations(site=construction_site(), corpus=changed, now=FIXED_NOW)


def test_changing_a_proved_rule_does_not_reuse_its_old_proof():
    rule = obligation()
    data = snapshot(obligations=[rule], stage=invoked_stage())
    changed = replace(rule, requirement=replace(rule.requirement, value=False))
    result = resolve_obligations(
        site=site(), corpus=replace(data, obligations=(changed,)), now=FIXED_NOW
    )
    assert not result.results
    assert result.excluded_unsourced


def test_changing_a_proved_band_cannot_reuse_its_quote_receipt(verified_corpus):
    band = next(b for b in verified_corpus.stage_bands if b.stage == 3)
    changed = replace(band, aqi_lower=1)
    result = resolve_obligations(
        site=construction_site(),
        corpus=replace(verified_corpus, stage_bands=(changed,)),
        reading=reading(value=50),
        now=FIXED_NOW,
    )
    assert result.stage_status.implied_stage is None
    assert result.stage is None


@pytest.mark.parametrize(
    "changes",
    [
        {"aqi_lower": 402},
        {"aqi_upper": 451},
        {"aqi_lower_inclusive": False},
        {"pollutant": "pm25"},
        {"stage": 5},
    ],
)
def test_stage_band_values_must_be_supported_by_the_quote(scratch, changes):
    path = scratch / "stage_bands/grap_stage_bands.json"
    data = json.loads(path.read_text())
    band = next(b for b in data["stage_bands"] if b["stage"] == 3)
    band.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert verify_corpus(scratch).has_failures
    with pytest.raises(CorpusIntegrityError, match="quote does not support"):
        LocalFileCorpus(scratch).snapshot()


def test_stage_iv_strict_boundary_cannot_be_replaced_by_a_derived_integer(scratch):
    path = scratch / "stage_bands/grap_stage_bands.json"
    data = json.loads(path.read_text())
    band = next(b for b in data["stage_bands"] if b["stage"] == 4)
    band.update(aqi_lower=451, aqi_lower_inclusive=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CorpusIntegrityError, match="quote does not support"):
        LocalFileCorpus(scratch).snapshot()


@pytest.mark.parametrize("wrong_stage", [1, 2, 4])
def test_a_stage_iii_quote_cannot_prove_another_ordinal(wrong_stage):
    quote = "The Sub-Committee hereby invokes Stage-III with immediate effect."
    assert quote_names_stage(quote, 3)
    assert not quote_names_stage(quote, wrong_stage)


def test_a_rule_stage_cannot_change_without_supporting_evidence(scratch):
    edit_rule(scratch, "grap3-cd-piling", lambda rule: rule.update(triggers_at_stage=2))
    with pytest.raises(CorpusIntegrityError, match="stage evidence"):
        LocalFileCorpus(scratch).snapshot()


def test_an_active_label_cannot_erase_a_recorded_revocation(scratch):
    path = scratch / "invoked_stage.json"
    payload = json.loads(path.read_text())
    payload["invoked"]["lifecycle"] = "active"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(scratch).invoked_stage()


def test_worker_counts_and_money_fields_do_not_change_resolution(verified_corpus):
    data = with_test_stage(verified_corpus, 3)
    profile = construction_site().to_profile()
    added = replace(profile, facts={**profile.facts, "active_workers": 9000, "amount_inr": 123456})
    baseline = resolve_obligations(site=profile, corpus=data, now=FIXED_NOW)
    result = resolve_obligations(site=added, corpus=data, now=FIXED_NOW)
    assert result == baseline
    rendered = json.dumps(resolution_to_dict(result)).lower()
    assert "123456" not in rendered and "9000" not in rendered
    for forbidden in (
        "amount_inr",
        "rupees",
        "tonnes of pollution",
        "pollution prevented",
        "pm2.5 reduced",
    ):
        assert forbidden not in rendered
    assert any(r.status is ObligationStatus.NOT_MET for r in result.results)


FORBIDDEN_IMPORTS = {
    "boto3",
    "botocore",
    "strands",
    "openai",
    "anthropic",
    "gemini",
    "claude",
    "google.generativeai",
    "google.genai",
    "langchain",
    "bedrock",
}


def forbidden_imports(source):
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and node.args:
            function = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if function in ("__import__", "import_module") and isinstance(
                node.args[0], ast.Constant
            ):
                names = [node.args[0].value]
        found.extend(
            name
            for name in names
            if isinstance(name, str)
            and any(name == banned or name.startswith(banned + ".") for banned in FORBIDDEN_IMPORTS)
        )
    return found


def test_resolver_and_its_domain_cannot_import_an_llm(core_root):
    files = [
        *(core_root / "resolver").rglob("*.py"),
        *(core_root / "domain").rglob("*.py"),
        core_root / "stages.py",
        core_root / "citations.py",
    ]
    assert all(not forbidden_imports(path.read_text(encoding="utf-8")) for path in files)


@pytest.mark.parametrize(
    "source",
    [
        "import boto3",
        "from strands import Agent",
        "__import__('openai')",
        "importlib.import_module('anthropic')",
    ],
)
def test_llm_import_guard_detects_real_breaches(source):
    assert forbidden_imports(source)


def test_real_replay_runs_with_llm_imports_and_network_unavailable(repo_root):
    program = """
import importlib.abc
import socket
import sys
class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'boto3', 'botocore', 'strands', 'openai', 'anthropic', 'google', 'gemini', 'claude'}:
            raise ImportError('External models unavailable')
sys.meta_path.insert(0, NoModels())
def no_network(*args, **kwargs):
    raise AssertionError('The deterministic engine attempted network access')
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network
from aadesh_cli.resolve import main
raise SystemExit(main(['--site', 'fixtures/sites/piling-site.json', '--replay',
                      'fixtures/replays/january-2026-stage-iii.json', '--now',
                      '2026-10-08T09:00:00+00:00']))
"""
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repo_root / "services")},
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["mode"] == "REPLAY"
    assert result["official_stage"] == 3
    assert result["summary"]["NOT_MET"] == 3
