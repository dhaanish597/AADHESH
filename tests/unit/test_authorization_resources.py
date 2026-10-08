"""The seam between the domain and Cedar: consent state, and the resources built from it.

Two things are being pinned here.

**Time is converted once, in one place.** Cedar compares integers; the domain carries
timezone-aware datetimes. That conversion is the only place a consent's window can be
silently shifted, and a shift is not a cosmetic bug -- an hour of drift is an hour in which a
worker's withdrawal has not taken effect. So a naive datetime is REFUSED rather than assumed
to be UTC: `datetime(2026, 1, 1, 9, 0)` in IST is a different instant from the same wall
clock in UTC, and guessing would turn a local-time mistake into an authorization decision.

**The built resource carries no personal data.** A Cedar entity store is a thing that gets
logged, snapshotted and reasoned about. It holds ids, a state and a site -- never a name, a
phone number or an identity document. There is nothing about the worker in it to leak.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_core.authorization.resources import (
    claim_assistance_resource,
    parchi_resource,
    site_resource,
    to_epoch_seconds,
)
from aadesh_core.consent import ClaimAssistanceContext, grant_consent, revoke_consent
from aadesh_core.ports.authz import EntityRef
from tests.support.authz_builders import parchi_domain

GRANTED_AT = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Consent state
# ---------------------------------------------------------------------------


def test_granting_consent_records_who_granted_it_to_whom():
    consent = grant_consent(
        context_id="ctx-1",
        parchi_id="parchi-001",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        granted_at=GRANTED_AT,
        ttl=timedelta(hours=24),
    )
    assert consent.worker_id == "wrk-1"
    assert consent.facilitator_id == "fac-1"
    assert consent.parchi_id == "parchi-001"
    assert consent.revoked_at is None
    assert consent.expires_at == GRANTED_AT + timedelta(hours=24)


def test_a_consent_cannot_be_granted_with_a_non_positive_ttl():
    """A consent that expires the moment it is granted authorizes nothing, and would be a
    silent denial rather than a configuration error."""
    with pytest.raises(ValueError, match="ttl"):
        grant_consent(
            context_id="ctx-1",
            parchi_id="parchi-001",
            worker_id="wrk-1",
            facilitator_id="fac-1",
            granted_at=GRANTED_AT,
            ttl=timedelta(0),
        )


def test_a_consent_cannot_name_the_worker_as_their_own_facilitator():
    """Assistance is a second person's act. A worker holding their own consent is a
    misconfiguration, and it would make `facilitator == principal` satisfiable by the
    worker themselves."""
    with pytest.raises(ValueError, match="facilitator"):
        grant_consent(
            context_id="ctx-1",
            parchi_id="parchi-001",
            worker_id="wrk-1",
            facilitator_id="wrk-1",
            granted_at=GRANTED_AT,
            ttl=timedelta(hours=1),
        )


def test_revoking_records_the_moment_it_happened():
    consent = grant_consent(
        context_id="ctx-1",
        parchi_id="parchi-001",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        granted_at=GRANTED_AT,
        ttl=timedelta(hours=24),
    )
    revoked = revoke_consent(consent, now=GRANTED_AT + timedelta(hours=1))
    assert revoked.revoked_at == GRANTED_AT + timedelta(hours=1)
    assert consent.revoked_at is None, "revoking must not mutate the original"


def test_revoking_an_already_revoked_consent_keeps_the_first_moment():
    """The withdrawal happened once. Overwriting the timestamp would move the evidence."""
    consent = grant_consent(
        context_id="ctx-1",
        parchi_id="parchi-001",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        granted_at=GRANTED_AT,
        ttl=timedelta(hours=24),
    )
    first = revoke_consent(consent, now=GRANTED_AT + timedelta(hours=1))
    second = revoke_consent(first, now=GRANTED_AT + timedelta(hours=5))
    assert second.revoked_at == GRANTED_AT + timedelta(hours=1)


# ---------------------------------------------------------------------------
# The resource builder
# ---------------------------------------------------------------------------


def _consent(**overrides) -> ClaimAssistanceContext:
    fields = dict(
        context_id="ctx-1",
        parchi_id="parchi-001",
        worker_id="wrk-1",
        facilitator_id="fac-1",
        granted_at=GRANTED_AT,
        ttl=timedelta(hours=24),
    )
    fields.update(overrides)
    return grant_consent(**fields)


def test_epoch_conversion_treats_the_instant_as_absolute():
    assert to_epoch_seconds(datetime(1970, 1, 1, tzinfo=UTC)) == 0
    assert to_epoch_seconds(GRANTED_AT) == int(GRANTED_AT.timestamp())


def test_a_naive_datetime_is_refused_rather_than_assumed_to_be_utc():
    """The bug this prevents: `datetime(2026,10,8,9,0)` read as IST is 09:00+05:30, which is
    03:30 UTC. Assuming UTC would move the consent window by five and a half hours."""
    with pytest.raises(ValueError, match="timezone"):
        to_epoch_seconds(datetime(2026, 10, 8, 9, 0))


def test_a_consent_is_built_into_a_cedar_resource_with_epoch_windows():
    resource = claim_assistance_resource(_consent())
    assert resource.entity_type == "ClaimAssistanceContext"
    assert resource.entity_id == "ctx-1"
    assert resource.attributes["consentGranted"] is True
    assert resource.attributes["grantedAt"] == to_epoch_seconds(GRANTED_AT)
    assert resource.attributes["expiresAt"] == to_epoch_seconds(GRANTED_AT + timedelta(hours=24))
    assert resource.attributes["facilitator"] == EntityRef("Principal", "fac-1")
    assert resource.attributes["worker"] == EntityRef("Worker", "wrk-1")
    assert resource.attributes["parchi"] == EntityRef("Parchi", "parchi-001")
    assert "revokedAt" not in resource.attributes


def test_a_revoked_consent_carries_the_revocation_instant():
    revoked = revoke_consent(_consent(), now=GRANTED_AT + timedelta(hours=2))
    resource = claim_assistance_resource(revoked)
    assert resource.attributes["revokedAt"] == to_epoch_seconds(GRANTED_AT + timedelta(hours=2))


def test_a_revoked_consent_still_reports_the_worker_did_grant_it():
    """`consentGranted` stays True across a revocation on purpose. The two facts are
    independent -- it WAS granted, and it WAS withdrawn -- and collapsing them would make
    "the worker shared this and then changed their mind" indistinguishable from "the worker
    never shared this"."""
    revoked = revoke_consent(_consent(), now=GRANTED_AT + timedelta(hours=2))
    assert claim_assistance_resource(revoked).attributes["consentGranted"] is True


def test_a_parchi_is_built_into_a_cedar_resource():
    parchi = parchi_domain(worker_id="wrk-1", site_id="site-001")
    resource = parchi_resource(parchi)
    assert resource.entity_type == "Parchi"
    assert resource.entity_id == parchi.parchi_id
    assert resource.attributes["worker"] == EntityRef("Principal", "wrk-1")
    assert resource.attributes["siteId"] == "site-001"
    assert resource.attributes["state"] == parchi.state.value


def test_a_parchi_with_no_workflow_execution_omits_the_reference():
    """None is honest for a parchi opened by hand. An invented execution id would be a
    fabricated provenance claim, which is exactly what this codebase refuses to produce."""
    parchi = parchi_domain(worker_id="wrk-1", site_id="site-001", execution_id=None)
    assert "execution" not in parchi_resource(parchi).attributes


def test_a_site_is_built_into_a_cedar_resource():
    resource = site_resource("site-001")
    assert resource.entity_type == "Site"
    assert resource.entity_id == "site-001"
    assert resource.attributes == {"siteId": "site-001"}


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


def test_no_built_resource_carries_personal_data():
    """The entity store is logged and snapshotted. Nothing in it may identify a person
    beyond an internal id, and nothing in it may be a type Cedar cannot represent."""
    parchi = parchi_domain(worker_id="wrk-1", site_id="site-001")
    resources = [parchi_resource(parchi), claim_assistance_resource(_consent()), site_resource("s")]

    forbidden = ("aadhaar", "phone", "mobile", "address", "pan", "bank", "account", "name")
    representable = (str, int, float, bool, EntityRef)
    for resource in resources:
        keys = " ".join(str(k).lower() for k in resource.attributes)
        assert not any(term in keys for term in forbidden), (
            f"{resource.entity_type} carries an attribute that looks personal: {keys}"
        )
        for key, value in resource.attributes.items():
            assert isinstance(value, representable), (
                f"{resource.entity_type}.{key} holds {value!r}, which Cedar cannot represent "
                f"and which would therefore be silently dropped."
            )
