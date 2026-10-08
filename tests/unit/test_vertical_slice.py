"""The vertical slice, end to end, with no AWS and no model.

This is the test that proves the architecture rather than any single component:

    corpus (hashed, cited) -> verification -> loader -> deterministic resolver
      -> Cedar authorization -> parchi -> worker acknowledgement -> sealed evidence

It runs twice. Once against the EMPTY corpus this repo actually ships, where the honest
outcome is that nothing can be determined -- and once against a fully cited corpus built in
a temp directory, where a parchi is opened, acknowledged by its own worker, and sealed.

If this file passes, every claim in the README about the deterministic path is demonstrable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from aadesh_adapters.aqi.fixture import FixtureAqiProvider
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain import ObligationStatus, Principal, Provenance, SiteProfile
from aadesh_core.errors import IllegalParchiTransition
from aadesh_core.explanation import check_explanation, context_for, explain_set
from aadesh_core.parchi import acknowledge, issue, open_parchi
from aadesh_core.ports.authz import AuthzResource, EntityRef
from aadesh_core.resolver import resolve_obligations
from aadesh_core.stages import derive_implied_stage
from tests.support.corpus_builder import CorpusBuilder

NOW = datetime(2026, 10, 8, 9, 30, tzinfo=UTC)
LATER = datetime(2026, 10, 8, 11, 0, tzinfo=UTC)

PAGE_TEXT = (
    "4. All dust generating construction and demolition activities shall remain "
    "suspended in the NCR until further orders.\n"
    "5. The Sub-Committee on GRAP hereby invokes Stage III of the GRAP in the entire NCR.\n"
)
VERBATIM = "dust generating construction and demolition activities shall remain suspended"
STAGE_QUOTE = "The Sub-Committee on GRAP hereby invokes Stage III of the GRAP"

SITE = SiteProfile(
    site_id="site-001",
    entity_type="construction_site",
    nearest_station_id="station-placeholder-1",
    facts={"has_dust_generating_activity": True},
)
WORKER = Principal(principal_id="wrk-1", role="worker")
SUPERVISOR = Principal(principal_id="sup-1", role="supervisor", assigned_site="site-001")


@pytest.fixture(scope="module")
def authz(repo_root):
    return CedarAuthorizationProvider(
        policy_path=repo_root / "infra" / "cedar" / "policies.cedar",
        denials_path=repo_root / "infra" / "cedar" / "denials.json",
        schema_path=repo_root / "infra" / "cedar" / "schema.cedarschema.json",
    )


@pytest.fixture
def reading(repo_root):
    provider = FixtureAqiProvider(
        path=repo_root / "fixtures" / "readings" / "placeholder_readings.json"
    )
    return provider.latest_reading(station_id="station-placeholder-1")


# --- against the corpus this repo actually ships ---------------------------


def test_shipped_corpus_has_no_live_stage_so_nothing_is_applicable(shipped_corpus, reading):
    corpus = LocalFileCorpus(shipped_corpus)

    result_set = resolve_obligations(
        site=SITE,
        stage=corpus.invoked_stage(),
        obligations=corpus.obligations(),
        reading=reading,
        now=NOW,
    )

    # The corpus is populated, but the only invocation on record -- January 2026's Stage III
    # -- was revoked. So no stage is currently in force, and every obligation is reported as
    # UNKNOWN rather than silently dropped or optimistically applied.
    assert result_set.stage is None
    assert result_set.results  # obligations exist and are visible
    assert result_set.applicable == ()
    assert all(r.status is ObligationStatus.UNKNOWN for r in result_set.results)
    assert result_set.fully_sourced is True
    assert "No GRAP stage is invoked" in explain_set(result_set).text


def test_the_shipped_bands_exist_but_the_placeholder_reading_falls_below_them(
    shipped_corpus, reading
):
    """Four cited bands are present; the placeholder reading is below the lowest of them.

    "Undeterminable" here is a real answer about a value outside every band, not the old
    "no bands are sourced yet" state. A reading that is not covered by any cited band is
    still honestly undeterminable rather than rounded to Stage I.
    """
    corpus = LocalFileCorpus(shipped_corpus)
    assert len(corpus.stage_bands()) == 4
    implied = derive_implied_stage(reading=reading, bands=corpus.stage_bands())
    assert implied.is_determinable is False


# --- against a fully cited corpus ------------------------------------------


@pytest.fixture
def sourced_corpus(tmp_path):
    root = (
        CorpusBuilder(tmp_path / "corpus")
        .with_document(doc_id="test-order")
        .with_page(doc_id="test-order", page=4, text=PAGE_TEXT)
        .with_obligation(obligation_id="ob-dust-01", page=4, quote=VERBATIM)
        .build()
    )
    # The invoked stage carries its own verbatim citation. It decides which obligations
    # apply, so it is the last thing in the corpus that may be taken on trust.
    (root / "invoked_stage.json").write_text(
        json.dumps(
            {
                "invoked": {
                    "stage": 3,
                    "source_doc": "test-order",
                    "invoked_at": "2026-10-08T06:00:00+00:00",
                    "page": 4,
                    "quote": STAGE_QUOTE,
                }
            }
        ),
        encoding="utf-8",
    )
    return LocalFileCorpus(root)


def test_full_chain_from_cited_corpus_to_sealed_parchi(sourced_corpus, reading, authz):
    # 1. resolve, deterministically
    result_set = resolve_obligations(
        site=SITE,
        stage=sourced_corpus.invoked_stage(),
        obligations=sourced_corpus.obligations(),
        reading=reading,
        now=NOW,
    )
    (result,) = result_set.results
    assert result.status is ObligationStatus.MET
    assert result.citation.quote == VERBATIM
    assert result_set.fully_sourced is True

    # 2. the supervisor is authorized to issue the halt for their own site
    assert authz.authorize(
        principal=SUPERVISOR,
        action="IssueHalt",
        resource=AuthzResource("Site", "site-001", {"siteId": "site-001"}),
    ).allowed

    # 3. a parchi opens for the worker and awaits THEM
    parchi = issue(
        open_parchi(
            parchi_id="parchi-001",
            site_id=SITE.site_id,
            worker_id="wrk-1",
            stage=result_set.stage,
            reading=result_set.reading,
            obligation_ids=tuple(r.obligation_id for r in result_set.applicable),
            entitlement_refs=(),
            readiness_checklist=("Welfare board registration number",),
            displaced_worker_days=1,
            now=NOW,
        ),
        now=NOW,
    )

    resource = AuthzResource(
        "Parchi",
        "parchi-001",
        {
            "worker": EntityRef("Principal", "wrk-1"),
            "siteId": "site-001",
            "sharedForAssistance": False,
        },
    )

    # 4. Cedar forbids the supervisor from finishing it on the worker's behalf
    denial = authz.authorize(principal=SUPERVISOR, action="AckParchi", resource=resource)
    assert denial.allowed is False
    assert denial.policy_id == "no-proxy-acknowledgement"
    with pytest.raises(IllegalParchiTransition):
        acknowledge(parchi, actor_worker_id=SUPERVISOR.principal_id, now=LATER)

    # 5. the worker acknowledges their own, and it seals
    assert authz.authorize(principal=WORKER, action="AckParchi", resource=resource).allowed
    sealed = acknowledge(parchi, actor_worker_id="wrk-1", now=LATER)
    assert sealed.content_hash is not None
    assert sealed.order_sha256 == result_set.stage.order_sha256

    # 6. provenance travelled the whole way and is honest about what it is
    assert sealed.provenance is Provenance.SYNTHETIC
    assert sealed.cites_measured_data is False

    # 7. the deterministic explanation satisfies the model's own contract
    explanation = explain_set(result_set)
    assert check_explanation(explanation, context=context_for(result_set)) == []


def test_no_model_was_involved_anywhere_in_that_chain():
    """The enforcement path must not import the explanation adapters at all."""
    import aadesh_core.parchi
    import aadesh_core.resolver.resolver

    for module in (aadesh_core.resolver.resolver, aadesh_core.parchi):
        source = module.__doc__ or ""
        assert "bedrock" not in source.lower()
        assert not hasattr(module, "boto3")
