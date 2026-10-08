"""INVARIANT: provenance cannot be laundered.

Aadesh ships with synthetic placeholder readings because no authoritative source is wired up
yet. The danger is obvious: a placeholder that loses its label somewhere between ingestion
and the parchi becomes a number that looks measured. A worker would then be holding a record
that cites a reading nobody took.

So provenance is required on every reading, derived (never passed separately) into the
obligation set and the parchi, and survives sealing.
"""

from __future__ import annotations

import pytest

from aadesh_core.domain import Provenance
from aadesh_core.parchi import acknowledge, issue, open_parchi
from aadesh_core.resolver import resolve_obligations
from tests.support.builders import FIXED_NOW, invoked_stage, obligation, reading, site

LATER = FIXED_NOW.replace(hour=11)


def _resolved(provenance: Provenance):
    return resolve_obligations(
        site=site(),
        stage=invoked_stage(),
        obligations=[obligation()],
        reading=reading(provenance=provenance),
        now=FIXED_NOW,
    )


@pytest.mark.parametrize(
    "provenance", [Provenance.SYNTHETIC, Provenance.MEASURED, Provenance.REPLAY]
)
def test_obligation_set_exposes_the_readings_provenance(provenance):
    assert _resolved(provenance).provenance is provenance


def test_obligation_set_without_a_reading_has_no_provenance():
    """Absent, not assumed. There is no default provenance to fall back on."""
    result_set = resolve_obligations(
        site=site(),
        stage=invoked_stage(),
        obligations=[obligation()],
        reading=None,
        now=FIXED_NOW,
    )
    assert result_set.provenance is None


@pytest.mark.parametrize(
    "provenance", [Provenance.SYNTHETIC, Provenance.MEASURED, Provenance.REPLAY]
)
def test_provenance_survives_the_whole_chain_into_a_sealed_parchi(provenance):
    result_set = _resolved(provenance)
    parchi = open_parchi(
        parchi_id="parchi-001",
        site_id=result_set.site_id,
        worker_id="worker-001",
        stage=result_set.stage,
        reading=result_set.reading,
        obligation_ids=tuple(r.obligation_id for r in result_set.applicable),
        entitlement_refs=(),
        readiness_checklist=(),
        displaced_worker_days=1,
        now=FIXED_NOW,
    )
    sealed = acknowledge(issue(parchi, now=FIXED_NOW), actor_worker_id="worker-001", now=LATER)
    assert sealed.provenance is provenance


def test_provenance_is_derived_from_the_reading_not_passed_separately():
    """There is no parameter through which a caller could relabel a synthetic reading."""
    import inspect

    params = inspect.signature(open_parchi).parameters
    assert "provenance" not in params, (
        "open_parchi must derive provenance from the reading; accepting it as an argument "
        "would make laundering a one-line change"
    )


def test_a_synthetic_parchi_knows_it_is_not_evidence_of_a_measurement():
    result_set = _resolved(Provenance.SYNTHETIC)
    parchi = open_parchi(
        parchi_id="parchi-001",
        site_id=result_set.site_id,
        worker_id="worker-001",
        stage=result_set.stage,
        reading=result_set.reading,
        obligation_ids=(),
        entitlement_refs=(),
        readiness_checklist=(),
        displaced_worker_days=1,
        now=FIXED_NOW,
    )
    assert parchi.cites_measured_data is False

    measured = open_parchi(
        parchi_id="parchi-002",
        site_id="site-001",
        worker_id="worker-001",
        stage=invoked_stage(),
        reading=reading(provenance=Provenance.MEASURED),
        obligation_ids=(),
        entitlement_refs=(),
        readiness_checklist=(),
        displaced_worker_days=1,
        now=FIXED_NOW,
    )
    assert measured.cites_measured_data is True
