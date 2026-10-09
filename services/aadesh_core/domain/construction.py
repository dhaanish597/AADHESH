"""The small, explicit input vocabulary needed by the construction corpus.

Each profile evaluates one described activity at a construction site. Other activities are
not implicitly absent or compliant. Category and activity values are source wording, not
legal classifications inferred by this class.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from math import isfinite
from typing import Any

from aadesh_core.domain.facts import UNKNOWN_FACT
from aadesh_core.domain.models import CONSTRUCTION_SITE, SiteProfile


@dataclass(frozen=True, slots=True)
class ConstructionSite:
    site_id: str
    in_ncr: bool | None = None
    plot_size_sqm: float | None = None
    registered_on_state_portal: bool | None = None
    remote_monitoring_requirements_met: bool | None = None
    activity_type: str | None = None
    activity_in_progress: bool | None = None
    is_minor_indoor_repair: bool | None = None
    project_category: str | None = None
    ancillary_to_category: str | None = None
    dust_mitigation_compliant: bool | None = None
    cd_waste_management_compliant: bool | None = None
    commission_directions_compliant: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.site_id, str) or not self.site_id.strip():
            raise ValueError("site_id must be a non-empty string")
        for descriptor in fields(self):
            value = getattr(self, descriptor.name)
            if value is None or value is UNKNOWN_FACT or descriptor.name == "site_id":
                continue
            annotation = str(descriptor.type)
            if annotation == "bool | None" and type(value) is not bool:
                raise ValueError(f"{descriptor.name} must be a boolean or null")
            if annotation == "str | None" and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{descriptor.name} must be a non-empty string or null")
            if annotation == "float | None" and (
                type(value) not in (int, float) or not isfinite(value) or value < 0
            ):
                raise ValueError(f"{descriptor.name} must be a finite non-negative number or null")

    def to_profile(self) -> SiteProfile:
        return SiteProfile(
            site_id=self.site_id,
            entity_type=CONSTRUCTION_SITE,
            nearest_station_id="",
            facts={
                descriptor.name: getattr(self, descriptor.name)
                for descriptor in fields(self)
                if descriptor.name != "site_id"
            },
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ConstructionSite:
        """Reject unexpected fields; a typo must not silently become a missing fact."""
        if not isinstance(payload, dict):
            raise ValueError("A site profile must be a JSON object")
        unexpected = payload.keys() - {descriptor.name for descriptor in fields(cls)}
        if unexpected:
            raise ValueError(f"Unknown construction-site facts: {', '.join(sorted(unexpected))}")
        if "site_id" not in payload:
            raise ValueError("site_id is required")
        return cls(**payload)
