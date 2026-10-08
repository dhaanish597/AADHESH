"""INVARIANTS: no GRAP threshold and no rupee amount is hardcoded in the deterministic core.

These two are the cheapest ways to destroy Aadesh's credibility, and both are tempting
shortcuts under a four-day clock:

    if aqi > 400: stage = 4          # a legal threshold, recalled from memory
    DISPLACEMENT_AMOUNT_INR = 8000   # a figure nobody can cite

Either would mean Aadesh is asserting law it cannot trace to a hashed source, while loudly
advertising that it can. The scanner backing these assertions is proven able to fail in
tests/unit/test_source_scan_guard.py -- without that companion file these tests would be
satisfied by a scanner that never found anything.
"""

from __future__ import annotations

import json

import pytest

from aadesh_core.domain import ImpliedStage, Provenance, SourceState
from aadesh_core.stages import derive_implied_stage
from tests.support.builders import FIXED_NOW, citation, reading
from tests.support.source_scan import scan_tree

GUARDED_PACKAGES = ["domain", "resolver", "parchi.py", "stages.py"]


def _scan(core_root, relative: str):
    target = core_root / relative
    assert target.exists(), f"guarded path {relative} is missing from aadesh_core"
    if target.is_file():
        from tests.support.source_scan import scan_file

        return scan_file(target, display_path=f"aadesh_core/{relative}")
    return scan_tree(target, relative_to=core_root.parent)


@pytest.mark.parametrize("relative", GUARDED_PACKAGES)
def test_no_hardcoded_legal_data_in_guarded_core_paths(core_root, relative):
    violations = _scan(core_root, relative)
    assert violations == [], "\n".join(["Hardcoded legal data found:", *map(str, violations)])


def test_no_currency_symbol_anywhere_in_the_core(core_root):
    violations = [
        v for v in scan_tree(core_root, relative_to=core_root.parent) if v.kind == "currency-symbol"
    ]
    assert violations == [], "\n".join(map(str, violations))


def test_no_money_named_constant_anywhere_in_the_core(core_root):
    violations = [
        v for v in scan_tree(core_root, relative_to=core_root.parent) if v.kind == "money-constant"
    ]
    assert violations == [], "\n".join(map(str, violations))


# --- the positive half: thresholds live in the corpus, and only there ------


def test_implied_stage_is_undeterminable_with_no_bands():
    """The honest Day 1 answer. Not a guess, not a default, not zero."""
    implied = derive_implied_stage(reading=reading(value=412.0), bands=[])
    assert isinstance(implied, ImpliedStage)
    assert implied.stage is None
    assert implied.is_determinable is False


def test_implied_stage_ignores_unsourced_bands(stage_band):
    """An unverified band is not a threshold, however plausible it looks."""
    implied = derive_implied_stage(
        reading=reading(value=412.0),
        bands=[stage_band(source_state=SourceState.UNSOURCED)],
    )
    assert implied.is_determinable is False


def test_implied_stage_uses_a_verified_band_and_carries_its_citation(stage_band):
    band = stage_band(source_state=SourceState.VERIFIED)
    implied = derive_implied_stage(reading=reading(value=412.0), bands=[band])
    assert implied.stage == band.stage
    assert implied.citation == band.citation


def test_implied_stage_is_undeterminable_without_a_reading(stage_band):
    implied = derive_implied_stage(
        reading=None, bands=[stage_band(source_state=SourceState.VERIFIED)]
    )
    assert implied.is_determinable is False


def test_shipped_corpus_declares_no_thresholds_outside_the_stage_bands_file(repo_root):
    """Thresholds have exactly one legitimate home. Assert the others stay clean."""
    for name in ["obligations/construction_site.json", "entitlements/cess_fund.json"]:
        payload = json.loads((repo_root / "corpus" / name).read_text(encoding="utf-8"))
        assert "aqi_lower" not in json.dumps(payload)
        assert "aqi_upper" not in json.dumps(payload)


@pytest.fixture
def stage_band():
    from aadesh_core.domain import StageBand

    def _build(**over):
        return StageBand(
            **{
                "stage": 3,
                "pollutant": "AQI",
                "aqi_lower": 401.0,
                "aqi_upper": None,
                "citation": citation(),
                "source_state": SourceState.UNSOURCED,
                **over,
            }
        )

    return _build


def test_provenance_enum_has_no_default():
    """A reading must state what it is; there is no safe default to fall back to."""
    assert set(Provenance) == {Provenance.MEASURED, Provenance.SYNTHETIC, Provenance.REPLAY}
    assert FIXED_NOW is not None  # keep the import honest
