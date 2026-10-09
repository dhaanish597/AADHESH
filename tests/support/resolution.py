"""Real rule snapshots and explicitly hypothetical invocation doubles for pure unit tests.

No invocation produced here is a CAQM order, and none is written to corpus/. Production and
CLI tests use only the real recorded invocation and revocation.
"""

from __future__ import annotations

from dataclasses import replace

from aadesh_core.domain import ConstructionSite, VerifiedCorpus
from tests.support.builders import invoked_stage


def with_test_stage(corpus: VerifiedCorpus, stage: int | None) -> VerifiedCorpus:
    if stage is None:
        return corpus
    invocation = invoked_stage(stage=stage)
    return replace(
        corpus,
        invocations=(*corpus.invocations, invocation),
        proved_citations=corpus.proved_citations | {invocation.citation},
        proved_invocations=corpus.proved_invocations | {invocation},
    )


def construction_site(**overrides) -> ConstructionSite:
    return ConstructionSite(
        **{
            "site_id": "test-site",
            "in_ncr": True,
            "plot_size_sqm": 750,
            "registered_on_state_portal": True,
            "remote_monitoring_requirements_met": True,
            "activity_type": "Piling works.",
            "activity_in_progress": True,
            "project_category": "Residential building",
            "dust_mitigation_compliant": True,
            "cd_waste_management_compliant": True,
            "commission_directions_compliant": True,
            **overrides,
        }
    )
