"""Cases A-I plus the factual conditions that the original encoding omitted."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from aadesh_core.domain import (
    ConstructionSite,
    InvocationLifecycle,
    ObligationStatus,
    ReplayContext,
    ResolutionMode,
    StageAgreement,
)
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.resolver import resolution_to_dict, resolve_obligations
from aadesh_core.stages import stage_status
from tests.support.builders import FIXED_NOW, reading
from tests.support.resolution import construction_site, with_test_stage

CASES = json.loads((Path(__file__).parents[1] / "fixtures/resolution/cases.json").read_text())
REPLAY = ReplayContext(invocation_date="2026-01-16", revocation_date="2026-01-22")


def resolve(corpus, *, stage=3, **facts):
    return resolve_obligations(
        site=construction_site(**facts),
        corpus=with_test_stage(corpus, stage),
        now=FIXED_NOW,
    )


def clause(result, rule_id):
    return next(r for r in result.results if r.obligation_id == rule_id)


@pytest.mark.parametrize("case", CASES, ids=lambda case: "CASE_" + case["case"])
def test_required_site_profile_cases(case, verified_corpus, repo_root):
    profile = json.loads((repo_root / "fixtures/sites" / case["site"]).read_text())
    profile.update(case.get("overrides", {}))
    result = resolve_obligations(
        site=ConstructionSite.from_dict(profile),
        corpus=with_test_stage(verified_corpus, case["official_stage"]),
        reading=reading(value=case["aqi"]) if "aqi" in case else None,
        now=FIXED_NOW,
    )
    assert result.stage_status.official_stage == case["official_stage"]
    assert len(result.results) == 8
    assert result.fully_sourced
    for rule_id, status in case.get("statuses", {}).items():
        assert clause(result, rule_id).status.name == status
    if "applicable" in case:
        assert [r.obligation_id for r in result.applicable] == case["applicable"]
    if "stage_status" in case:
        assert result.stage_status.status.value == case["stage_status"]
    if "implied_stage" in case:
        assert result.stage_status.implied_stage == case["implied_stage"]


@pytest.mark.parametrize(
    "area,registered,monitoring,ongoing,expected",
    [
        (499, False, False, True, ObligationStatus.NOT_APPLICABLE),
        (500, False, True, True, ObligationStatus.NOT_MET),
        (500, True, False, True, ObligationStatus.NOT_MET),
        (500, True, True, True, ObligationStatus.MET),
        (500, None, True, True, ObligationStatus.UNKNOWN),
        (500, True, None, True, ObligationStatus.UNKNOWN),
        (None, False, False, True, ObligationStatus.UNKNOWN),
        (500, False, False, False, ObligationStatus.MET),
    ],
)
def test_registration_preserves_all_conditions(
    verified_corpus,
    area,
    registered,
    monitoring,
    ongoing,
    expected,
):
    result = resolve(
        verified_corpus,
        stage=1,
        plot_size_sqm=area,
        registered_on_state_portal=registered,
        remote_monitoring_requirements_met=monitoring,
        activity_in_progress=ongoing,
    )
    assert clause(result, "grap1-cd-large-project-registration").status is expected


@pytest.mark.parametrize(
    "activity,rule_id",
    [
        ("All demolition works.", "grap3-cd-demolition"),
        ("Piling works.", "grap3-cd-piling"),
        (
            "Movement of vehicles carrying construction materials or C&D waste on unpaved roads.",
            "grap3-cd-unpaved-roads",
        ),
    ],
)
def test_each_restricted_activity_requires_a_halt_or_the_complete_exception(
    verified_corpus,
    activity,
    rule_id,
):
    ongoing = resolve(verified_corpus, activity_type=activity)
    halted = resolve(verified_corpus, activity_type=activity, activity_in_progress=False)
    exempt = resolve(
        verified_corpus,
        activity_type=activity,
        project_category="Hospitals/ health care facilities",
    )
    conditional = resolve(
        verified_corpus,
        activity_type=activity,
        project_category="Hospitals/ health care facilities",
        commission_directions_compliant=None,
    )
    assert clause(ongoing, rule_id).status is ObligationStatus.NOT_MET
    assert clause(halted, rule_id).status is ObligationStatus.MET
    assert clause(exempt, rule_id).status is ObligationStatus.MET
    assert clause(conditional, rule_id).status is ObligationStatus.UNKNOWN
    assert clause(ongoing, "grap3-cd-restricted-activities").status is ObligationStatus.NOT_MET


@pytest.mark.parametrize(
    "missing_fact",
    [
        "dust_mitigation_compliant",
        "cd_waste_management_compliant",
        "commission_directions_compliant",
    ],
)
def test_project_category_alone_never_satisfies_the_exception(verified_corpus, missing_fact):
    result = resolve(
        verified_corpus,
        project_category="Hospitals/ health care facilities",
        **{missing_fact: None},
    )
    assert clause(result, "grap3-cd-piling").status is ObligationStatus.UNKNOWN
    assert clause(result, "grap3-cd-permitted-categories-only").status is ObligationStatus.UNKNOWN


def test_noncompliant_exempt_project_must_stop(verified_corpus):
    result = resolve(
        verified_corpus,
        project_category="Hospitals/ health care facilities",
        commission_directions_compliant=False,
    )
    assert clause(result, "grap3-cd-piling").status is ObligationStatus.NOT_MET


@pytest.mark.parametrize(
    "parent,expected",
    [
        (None, ObligationStatus.UNKNOWN),
        ("Residential building", ObligationStatus.NOT_MET),
        ("Hospitals/ health care facilities", ObligationStatus.MET),
    ],
)
def test_ancillary_work_needs_the_specific_parent_category(verified_corpus, parent, expected):
    result = resolve(
        verified_corpus, project_category="Ancillary activities", ancillary_to_category=parent
    )
    assert clause(result, "grap3-cd-piling").status is expected


@pytest.mark.parametrize(
    "activity",
    [
        "Cement, Plaster / other coatings",
        "Cutting / grinding and fixing of tiles, stones and other flooring materials",
    ],
)
def test_indoor_repair_exception_is_an_explicit_fact(verified_corpus, activity):
    unknown = resolve(verified_corpus, activity_type=activity)
    minor = resolve(verified_corpus, activity_type=activity, is_minor_indoor_repair=True)
    major = resolve(verified_corpus, activity_type=activity, is_minor_indoor_repair=False)
    assert clause(unknown, "grap3-cd-restricted-activities").status is ObligationStatus.UNKNOWN
    assert clause(minor, "grap3-cd-restricted-activities").status is ObligationStatus.NOT_APPLICABLE
    assert clause(major, "grap3-cd-restricted-activities").status is ObligationStatus.NOT_MET


@pytest.mark.parametrize(
    "activity",
    [
        "Minor welding activities for MEP works",
        "Repairing of potholes",
        "Movement of empty vehicles on an unpaved road",
    ],
)
def test_narrow_restrictions_do_not_expand_to_other_activities(verified_corpus, activity):
    result = resolve(verified_corpus, activity_type=activity)
    assert (
        clause(result, "grap3-cd-restricted-activities").status is ObligationStatus.NOT_APPLICABLE
    )
    assert clause(result, "grap3-cd-unpaved-roads").status is ObligationStatus.NOT_APPLICABLE


def test_permitted_categories_ambiguity_is_visible_and_does_not_invent_a_ban(verified_corpus):
    result = resolve(verified_corpus, activity_type="Relatively less polluting construction work")
    decision = clause(result, "grap3-cd-permitted-categories-only")
    assert decision.status is ObligationStatus.UNKNOWN
    assert "source clarification" in decision.reason
    assert any("other than" in c.quote for c in decision.evidence)
    assert any("only for the following categories" in c.quote for c in decision.evidence)


def test_stage_iv_adds_a_restriction_to_linear_projects_only(verified_corpus):
    linear = resolve(verified_corpus, stage=4, project_category="Linear public projects")
    hospital = resolve(
        verified_corpus, stage=4, project_category="Hospitals/ health care facilities"
    )
    assert clause(linear, "grap4-cd-linear-projects").status is ObligationStatus.NOT_MET
    assert clause(hospital, "grap4-cd-linear-projects").status is ObligationStatus.NOT_APPLICABLE
    assert clause(hospital, "grap3-cd-piling").status is ObligationStatus.MET
    assert clause(linear, "grap1-cd-dust-mitigation").applicable is True


def test_unknown_stage_iv_activity_cannot_satisfy_the_rule(verified_corpus):
    result = resolve(
        verified_corpus, stage=4, project_category="Linear public projects", activity_type=None
    )
    assert clause(result, "grap4-cd-linear-projects").status is ObligationStatus.UNKNOWN


def test_stopping_work_does_not_imply_dust_controls_are_met(verified_corpus):
    result = resolve(
        verified_corpus, stage=1, activity_in_progress=False, dust_mitigation_compliant=None
    )
    assert clause(result, "grap1-cd-dust-mitigation").status is ObligationStatus.UNKNOWN


def test_unknown_location_is_unknown_and_known_outside_ncr_is_not_applicable(verified_corpus):
    unknown = resolve(verified_corpus, in_ncr=None)
    outside = resolve(verified_corpus, in_ncr=False)
    assert all(r.status is not ObligationStatus.MET for r in unknown.results)
    assert all(r.status is ObligationStatus.NOT_APPLICABLE for r in outside.results)


def test_discrepancy_keeps_both_stages_and_the_official_basis(verified_corpus):
    result = resolve_obligations(
        site=construction_site(),
        corpus=with_test_stage(verified_corpus, 2),
        reading=reading(value=420),
        now=FIXED_NOW,
    )
    assert result.stage_status.status is StageAgreement.DISCREPANCY
    assert result.stage_status.official_stage == 2
    assert result.stage_status.implied_stage == 3
    assert "does not infer legal activation from AQI" in result.stage_status.reason
    assert clause(result, "grap3-cd-piling").status is ObligationStatus.NOT_APPLICABLE
    wire = resolution_to_dict(result)
    assert (wire["official_stage"], wire["implied_stage"], wire["stage_status"]) == (
        2,
        3,
        "DISCREPANCY",
    )


def test_aqi_cannot_create_an_official_invocation(verified_corpus):
    result = resolve_obligations(
        site=construction_site(), corpus=verified_corpus, reading=reading(value=420), now=FIXED_NOW
    )
    assert result.stage is None
    assert result.stage_status.implied_stage == 3
    assert result.applicable == ()
    assert "no verified current CAQM invocation" in result.stage_status.reason


def test_a_pollutant_concentration_is_not_an_aqi_value(verified_corpus):
    result = resolve_obligations(
        site=construction_site(),
        corpus=verified_corpus,
        reading=reading(parameter="pm25", value=420),
        now=FIXED_NOW,
    )
    assert result.stage_status.implied_stage is None
    assert result.stage is None


@pytest.mark.parametrize("aqi,expected", [(450, 3), (450.5, 4), (451, 4)])
def test_stage_iv_uses_the_cited_strict_boundary_without_rounding(verified_corpus, aqi, expected):
    result = resolve_obligations(
        site=construction_site(), corpus=verified_corpus, reading=reading(value=aqi), now=FIXED_NOW
    )
    assert result.stage_status.implied_stage == expected
    assert result.stage is None
    assert not result.applicable


def test_current_mode_does_not_replay_history_even_with_a_historical_clock(verified_corpus):
    result = resolve_obligations(
        site=construction_site(),
        corpus=verified_corpus,
        now=datetime.fromisoformat("2026-01-18T12:00:00+05:30"),
    )
    assert result.stage is None
    assert result.mode is ResolutionMode.CURRENT
    assert result.applicable == ()


def test_explicit_historical_replay_is_labelled_on_every_result(verified_corpus):
    result = resolve_obligations(
        site=construction_site(), corpus=verified_corpus, now=FIXED_NOW, replay=REPLAY
    )
    assert result.mode is ResolutionMode.REPLAY
    assert result.stage.stage == 3
    assert result.stage.lifecycle is InvocationLifecycle.REVOKED
    assert not result.stage.is_current
    assert result.current_stage is None
    assert all(
        r.mode is ResolutionMode.REPLAY and "Historical scenario replay" in r.reason
        for r in result.results
    )
    assert "not established" in result.replay_notice
    assert "not a current invocation or proof of historical obligations" in result.replay_notice
    wire = resolution_to_dict(result)
    assert wire["mode"] == "REPLAY"
    assert wire["current_official_stage"] == "NONE"
    assert wire["official_invocation"]["revocation_citation"]["source_hash"]
    assert (
        resolve_obligations(site=construction_site(), corpus=verified_corpus, now=FIXED_NOW).stage
        is None
    )


@pytest.mark.parametrize("at", ["2026-01-15T23:59:59+05:30", "2026-01-22T00:00:00+05:30"])
def test_replay_refuses_an_instant_outside_the_verified_interval(verified_corpus, at):
    with pytest.raises(CorpusIntegrityError, match="outside"):
        resolve_obligations(
            site=construction_site(),
            corpus=verified_corpus,
            now=FIXED_NOW,
            replay=replace(REPLAY, at=datetime.fromisoformat(at)),
        )


def test_replay_dates_must_match_the_actual_record(verified_corpus):
    with pytest.raises(CorpusIntegrityError, match="match one verified"):
        resolve_obligations(
            site=construction_site(),
            corpus=verified_corpus,
            now=FIXED_NOW,
            replay=replace(REPLAY, revocation_date="2026-01-23"),
        )


def test_stage_display_cannot_relabel_revoked_history_as_current(verified_corpus):
    historical = verified_corpus.invocations[0]
    state = stage_status(
        invoked=historical, reading=reading(value=420), bands=verified_corpus.stage_bands
    )
    assert state.official_stage is None
    assert state.status is StageAgreement.DISCREPANCY


def test_current_invocation_cannot_take_effect_before_its_order(verified_corpus):
    future = with_test_stage(verified_corpus, 3)
    now = FIXED_NOW.replace(hour=8)
    result = resolve_obligations(site=construction_site(), corpus=future, now=now)
    assert result.stage is None
    assert result.applicable == ()


def test_every_applicable_obligation_carries_primary_and_condition_provenance(verified_corpus):
    result = resolve(verified_corpus, stage=4, project_category="Linear public projects")
    for obligation in result.applicable:
        assert obligation.source_doc
        assert obligation.source_page > 0
        assert obligation.source_quote
        assert len(obligation.source_hash) == 64
        assert obligation.evidence
        assert all(c in verified_corpus.proved_citations for c in obligation.evidence)


def test_same_site_snapshot_and_time_produce_identical_complete_output(verified_corpus):
    first = resolve(verified_corpus)
    second = resolve(verified_corpus)
    assert first == second
    assert resolution_to_dict(first) == resolution_to_dict(second)
