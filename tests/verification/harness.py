"""The full-stack fixture the Prompt 8 verification tests drive.

One job: stand up everything the chain needs -- a re-proved corpus with a *live* official
invocation, the resolver, the standing-order machine, the parchi service, the Cedar adapter and
an audit sink -- so a test can walk CAQM source -> sealed evidence without re-deriving the
wiring each time, and without faking any component that is under test.

Deliberate choices:

  * The corpus written here is a **test corpus**, built under tmp_path. It is never the shipped
    corpus, and no test in this package writes to `corpus/`. `docs/verification.md` says so in
    public.
  * The stage bands and the invocation sentence are copied from the real shipped records so the
    same validators (`validate_stage_band_evidence`, `quote_names_stage`, the verifier) accept
    them for the same reasons the real corpus is accepted.
  * A revoked invocation is NOT synthesised here. The historical replay tests use the real
    recorded 16.01.2026 invocation and 22.01.2026 revocation in `corpus/`, because fabricating a
    revocation is exactly the kind of shortcut this package exists to catch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_core.domain import (
    InvokedStage,
    Provenance,
    SiteProfile,
    StationReading,
)
from aadesh_core.ports.authz import AuthzResource
from tests.support.corpus_builder import CorpusBuilder

# --- fixed instants ----------------------------------------------------------

#: One clock for the whole package. Every test states its own `now` explicitly, so a failing
#: test names the instant it was reasoning about rather than inheriting "today".
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)

# --- the test corpus ---------------------------------------------------------

#: doc_id of the synthetic CAQM order the live-invocation fixtures cite.
ORDER_DOC = "test-grap-order"
INVOKE_PAGE = 1
RULE_PAGE = 4
OBLIGATION_ID = "test-ob-01"

#: Mirror of the shipped band wording, so `validate_stage_band_evidence` accepts these for the
#: same reasons it accepts the real ones (bounds encoded, stage named).
#:
#: The en dashes and curly quotes are not typos and must not be "corrected" to ASCII: the real
#: CAQM schedule uses them, and a fixture written in plain ASCII would be proved by a different
#: path than the shipped corpus is. `RUF001` is silenced per line for that reason.
BAND_QUOTES: dict[int, str] = {
    1: "Stage I – ‘Poor’ Air Quality (DELHI AQI ranging between 201-300)",  # noqa: RUF001
    2: "Stage II – ‘Very Poor’ Air Quality (DELHI AQI ranging between 301-400)",  # noqa: RUF001
    3: "Stage III – ‘Severe’ Air Quality (DELHI AQI ranging between 401-450)",  # noqa: RUF001
    4: "Stage IV – ‘Severe +’ Air Quality (DELHI AQI > 450)",  # noqa: RUF001
}
BAND_BOUNDS: dict[int, tuple[float, float | None]] = {
    1: (201, 300),
    2: (301, 400),
    3: (401, 450),
    4: (450, None),
}
STAGE_ROMAN: dict[int, str] = {1: "I", 2: "II", 3: "III", 4: "IV"}

#: The rule's own sentence. `rule_entry` treats the entry's primary `quote` as the "clause"
#: evidence every predicate literal is checked against, so this text must be on RULE_PAGE.
RULE_QUOTE = (
    "Construction and demolition activities shall be suspended across the National Capital "
    "Region while this stage remains in force."
)


def invocation_quote(stage: int) -> str:
    return (
        "the Sub Committee on GRAP hereby decide to invoke all actions under "
        f"Stage-{STAGE_ROMAN[stage]} of the extant schedule of GRAP, with immediate effect in "
        "right earnest by all the agencies concerned in Delhi-NCR."
    )


def build_corpus(
    root: Path,
    *,
    invoked_stage: int = 3,
    bands: tuple[int, ...] = (3,),
) -> Path:
    """Write a re-provable corpus whose official invocation is CURRENT.

    `bands` names which stage bands to encode. Passing both the invoked stage and a lower one
    is how the "AQI implies a higher stage than the order invoked" case is set up.
    """
    page_one = "\n".join(
        [
            "Order under Section 5 of the Air (Prevention and Control of Pollution) Act, 1981.",
            *(BAND_QUOTES[stage] for stage in bands),
            invocation_quote(invoked_stage),
        ]
    )
    builder = (
        CorpusBuilder(root)
        .with_document(doc_id=ORDER_DOC)
        .with_page(doc_id=ORDER_DOC, page=INVOKE_PAGE, text=page_one)
        .with_page(doc_id=ORDER_DOC, page=RULE_PAGE, text=RULE_QUOTE)
        .with_obligation(
            obligation_id=OBLIGATION_ID, doc_id=ORDER_DOC, page=RULE_PAGE, quote=RULE_QUOTE
        )
    )
    corpus = builder.build()
    _write(
        corpus / "stage_bands" / "grap_stage_bands.json",
        {
            "stage_bands": [
                {
                    "stage": stage,
                    "pollutant": "AQI",
                    "aqi_lower": BAND_BOUNDS[stage][0],
                    "aqi_upper": BAND_BOUNDS[stage][1],
                    "source_doc": ORDER_DOC,
                    "page": INVOKE_PAGE,
                    "quote": BAND_QUOTES[stage],
                }
                for stage in bands
            ]
        },
    )
    _write(
        corpus / "invoked_stage.json",
        {
            "invoked": {
                "stage": invoked_stage,
                "source_doc": ORDER_DOC,
                "page": INVOKE_PAGE,
                "quote": invocation_quote(invoked_stage),
                "invoked_at": "2026-10-08T09:00:00+00:00",
                "lifecycle": "active",
            }
        },
    )
    # A live snapshot is only handed out if it re-proves; a fixture that silently drifted from
    # its own citations would make every test below meaningless.
    LocalFileCorpus(corpus).snapshot()
    return corpus


def live_invocation(corpus: Path) -> InvokedStage:
    """The CURRENT invocation as the production loader hands it to the resolver."""
    invocation = LocalFileCorpus(corpus).invoked_stage()
    assert invocation is not None, "the fixture corpus was supposed to carry a current invocation"
    return invocation


def reading(value: float = 420.0, *, parameter: str = "AQI") -> StationReading:
    return StationReading(
        station_id="station-001",
        parameter=parameter,
        value=value,
        observed_at=NOW,
        ingested_at=NOW,
        provenance=Provenance.MEASURED,
    )


def site(*, site_id: str = "site-001", **facts: object) -> SiteProfile:
    return SiteProfile(
        site_id=site_id,
        entity_type="construction_site",
        nearest_station_id="station-001",
        facts={"in_ncr": True, "activity_in_progress": False, **facts},
    )


# --- the rest of the stack ---------------------------------------------------


@dataclass
class Stack:
    """Every collaborator the chain needs, built the way production builds them."""

    cedar: CedarAuthorizationProvider
    parchi_store: InMemoryParchiStore
    tokens: InMemoryAcknowledgementTokenStore
    ledger: InMemoryIdempotencyLedger
    audit: RecordingAuditLog


def stack(repo_root: Path) -> Stack:
    cedar_root = repo_root / "infra" / "cedar"
    return Stack(
        cedar=CedarAuthorizationProvider(
            policy_path=cedar_root / "policies.cedar",
            denials_path=cedar_root / "denials.json",
            schema_path=cedar_root / "schema.cedarschema.json",
        ),
        parchi_store=InMemoryParchiStore(),
        tokens=InMemoryAcknowledgementTokenStore(),
        ledger=InMemoryIdempotencyLedger(),
        audit=RecordingAuditLog(),
    )


def authz_resource(*, entity_type: str, entity_id: str, **attributes: object) -> AuthzResource:
    return AuthzResource(entity_type=entity_type, entity_id=entity_id, attributes=dict(attributes))


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


__all__ = [
    "BAND_BOUNDS",
    "BAND_QUOTES",
    "INVOKE_PAGE",
    "NOW",
    "OBLIGATION_ID",
    "ORDER_DOC",
    "RULE_PAGE",
    "RULE_QUOTE",
    "STAGE_ROMAN",
    "VALID_FROM",
    "VALID_UNTIL",
    "Stack",
    "authz_resource",
    "build_corpus",
    "invocation_quote",
    "live_invocation",
    "reading",
    "site",
    "stack",
]
