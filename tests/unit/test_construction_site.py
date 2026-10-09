"""Explicit site inputs, without convenient coercions or invented facts."""

from __future__ import annotations

import pytest

from aadesh_core.domain import ConstructionSite


def test_missing_and_json_null_remain_unknown():
    site = ConstructionSite.from_dict({"site_id": "site", "dust_mitigation_compliant": None})
    assert site.dust_mitigation_compliant is None
    assert site.in_ncr is None
    assert site.registered_on_state_portal is None
    assert site.to_profile().fact("dust_mitigation_compliant") is None


@pytest.mark.parametrize(
    "facts",
    [
        {"in_ncr": 1},
        {"in_ncr": "true"},
        {"activity_in_progress": 0},
        {"plot_size_sqm": True},
        {"plot_size_sqm": "500"},
        {"plot_size_sqm": -1},
        {"plot_size_sqm": float("nan")},
        {"plot_size_sqm": float("inf")},
        {"activity_type": ""},
        {"project_category": []},
    ],
)
def test_invalid_fact_types_are_rejected_without_coercion(facts):
    with pytest.raises(ValueError):
        ConstructionSite.from_dict({"site_id": "site", **facts})


def test_worker_count_is_not_a_legal_site_fact():
    with pytest.raises(ValueError, match="active_workers"):
        ConstructionSite.from_dict({"site_id": "site", "active_workers": 500})


def test_project_area_cannot_be_silently_substituted_for_plot_size():
    with pytest.raises(ValueError, match="project_area_sq_m"):
        ConstructionSite.from_dict({"site_id": "site", "project_area_sq_m": 750})
