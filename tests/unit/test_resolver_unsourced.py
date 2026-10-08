"""INVARIANT: an unsourced clause cannot enter resolution.

A corpus entry whose quote has not been verified against hashed source bytes must never
produce an obligation result. If it did, Aadesh would be asserting a legal obligation on the
strength of text nobody has proved exists in an official order -- which is precisely the
failure mode the whole provenance apparatus exists to prevent.

Exclusion must also be LOUD. Silently dropping an unsourced clause would let an incomplete
corpus look like a clean bill of health.
"""

from __future__ import annotations

from aadesh_core.domain import Obligation, SourceState
from aadesh_core.resolver import resolve_obligations
from tests.support.builders import FIXED_NOW, citation, invoked_stage, obligation, reading, site


def _resolve(obligations):
    return resolve_obligations(
        site=site(),
        stage=invoked_stage(),
        obligations=obligations,
        reading=reading(),
        now=FIXED_NOW,
    )


def test_unsourced_obligation_produces_no_result():
    result_set = _resolve([obligation(source_state=SourceState.UNSOURCED)])
    assert result_set.results == ()


def test_unsourced_obligation_is_reported_as_excluded():
    result_set = _resolve(
        [obligation(obligation_id="ob-unsourced", source_state=SourceState.UNSOURCED)]
    )
    (excluded,) = result_set.excluded_unsourced
    assert excluded.obligation_id == "ob-unsourced"
    assert "not verified" in excluded.reason.lower()


def test_source_state_defaults_to_unsourced():
    """Fail-safe. An Obligation that never went through verification must be excluded by
    default, so forgetting to set the flag cannot silently admit unproven text."""
    raw = Obligation(
        obligation_id="ob-default",
        entity_types=("construction_site",),
        triggers_at_stage=3,
        label="Built without stating source_state",
        field="has_dust_generating_activity",
        operator="eq",
        value=True,
        citation=citation(),
        issues_parchi=True,
    )
    assert raw.source_state is SourceState.UNSOURCED

    result_set = _resolve([raw])
    assert result_set.results == ()
    assert len(result_set.excluded_unsourced) == 1


def test_verified_obligation_does_enter_resolution():
    result_set = _resolve([obligation(source_state=SourceState.VERIFIED)])
    assert len(result_set.results) == 1
    assert result_set.excluded_unsourced == ()


def test_mixed_corpus_separates_verified_from_unsourced():
    result_set = _resolve(
        [
            obligation(obligation_id="ob-ok", source_state=SourceState.VERIFIED),
            obligation(obligation_id="ob-bad", source_state=SourceState.UNSOURCED),
        ]
    )
    assert [r.obligation_id for r in result_set.results] == ["ob-ok"]
    assert [e.obligation_id for e in result_set.excluded_unsourced] == ["ob-bad"]


def test_obligation_for_a_different_entity_type_is_not_resolved():
    """Scope is one entity type. Anything else is out of scope by definition."""
    result_set = _resolve([obligation(entity_types=("school",))])
    assert result_set.results == ()
    assert result_set.excluded_unsourced == ()


def test_set_knows_whether_it_is_safe_to_act_on():
    """An obligation set built from a corpus with any unsourced entry is not claim-ready."""
    clean = _resolve([obligation(source_state=SourceState.VERIFIED)])
    dirty = _resolve(
        [
            obligation(obligation_id="ob-ok", source_state=SourceState.VERIFIED),
            obligation(obligation_id="ob-bad", source_state=SourceState.UNSOURCED),
        ]
    )
    assert clean.fully_sourced is True
    assert dirty.fully_sourced is False
