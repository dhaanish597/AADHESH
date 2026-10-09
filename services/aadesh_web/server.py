"""The Aadesh local web API: a thin adapter over the deterministic core.

This is the "local HTTP server" the architecture doc promised -- the same core that would sit
behind Lambda handlers, exposed to the Next.js frontend as JSON. It adds no rules of its own:

  * the stage, the obligations and their citations come from `resolve_obligations` over a
    verification snapshot of `corpus/`;
  * every refusal (a supervisor acknowledging a worker's parchi, a facilitator reading a
    record) comes from the REAL Cedar engine, evaluated from `infra/cedar/policies.cedar`;
  * `verification` runs `run_verify` in-process, so the screen shows the actual exit code
    rather than a claim about it.

State is in-memory and lives for the life of the process. This is a local demonstration
adapter: there is no database, no session, and no persistence, by design.
"""

from __future__ import annotations

import argparse
import io
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from aadesh_adapters.audit.recording import RecordingAuditLog
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_adapters.store.memory import InMemoryParchiStore
from aadesh_adapters.store.memory_ack import (
    InMemoryAcknowledgementTokenStore,
    InMemoryIdempotencyLedger,
)
from aadesh_cli.verify import run_verify
from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import ASSIST_CLAIM, VIEW_PARCHI
from aadesh_core.consent import grant_consent, request_assistance
from aadesh_core.domain import (
    ConstructionSite,
    InvocationLifecycle,
    ObligationStatus,
    Principal,
    Provenance,
    ReplayContext,
    ResolutionResult,
    StationReading,
)
from aadesh_core.domain.enums import StageMatch, StandingOrderAction, StandingOrderStatus
from aadesh_core.errors import AadeshError, AuthorizationDenied, TokenRejected, WrongWorker
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    Roster,
    RosterEntry,
    WorkflowExecution,
    assist_claim,
    create_parchis_for_roster,
    describe_pending_parchi,
)
from aadesh_core.parchi_ack.service import resolve_parchi_for_payload
from aadesh_core.resolver import resolution_to_dict, resolve_obligations
from aadesh_core.standing_order import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    activate,
    confirm,
    project_status,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = PROJECT_ROOT / "corpus"
CEDAR_DIR = PROJECT_ROOT / "infra" / "cedar"

SITE_ID = "example-piling-site"
SITE_LABEL = "Construction Site — Delhi-NCR"
SITE_FIXTURE = PROJECT_ROOT / "fixtures" / "sites" / "piling-site.json"
SUPERVISOR_ID = "supervisor-001"
FACILITATOR_ID = "facilitator-001"

REPLAY_INVOCATION_DATE = "2026-01-16"
REPLAY_REVOCATION_DATE = "2026-01-22"

# The demonstration roster. Site data, not legal corpus data: worker count is not an
# entitlement multiplier, and `registered` is documentation readiness only -- it is NOT a
# claim that anyone is entitled to any sum.
WORKER_COUNT = 34
REGISTERED_WORKERS = 27
MAX_READING_AGE = timedelta(minutes=90)

OBSERVATIONS = {
    "aligned": PROJECT_ROOT / "fixtures" / "observations" / "rohini-aqi-aligned.json",
    "divergent": PROJECT_ROOT / "fixtures" / "observations" / "rohini-aqi-divergent.json",
}


# ---------------------------------------------------------------------------
# Serialisation helpers (presentation only; no decisions are made here)
# ---------------------------------------------------------------------------


def _citation_dict(citation: Any) -> dict[str, Any] | None:
    if citation is None:
        return None
    return {
        "source_doc": citation.source_doc,
        "source_page": citation.page,
        "source_quote": citation.quote,
        "source_hash": citation.source_hash,
        "short_hash": (citation.source_hash or "")[:8],
    }


def _parchi_dict(parchi: Parchi) -> dict[str, Any]:
    return {
        "parchi_id": parchi.parchi_id,
        "site_id": parchi.site_id,
        "worker_id": parchi.worker_id,
        "state": parchi.state.value,
        "schema_version": parchi.schema_version,
        "created_at": parchi.created_at.isoformat(),
        "issued_at": parchi.issued_at.isoformat() if parchi.issued_at else None,
        "acknowledged_at": parchi.acknowledged_at.isoformat() if parchi.acknowledged_at else None,
        "acknowledged_by": parchi.acknowledged_by,
        "acknowledgement_method": (
            parchi.acknowledgement_method.value if parchi.acknowledgement_method else None
        ),
        "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
        "content_hash": parchi.content_hash,
        "stage": parchi.stage.stage if parchi.stage else None,
        "provenance": parchi.provenance.value if parchi.provenance else None,
        "cites_measured_data": parchi.cites_measured_data,
        "obligation_ids": list(parchi.obligation_ids),
        "entitlement_refs": list(parchi.entitlement_refs),
        "readiness_checklist": list(parchi.readiness_checklist),
        "displaced_worker_days": parchi.displaced_worker_days,
        "source_document_ids": list(parchi.source_document_ids),
        "source_hashes": list(parchi.source_hashes),
        "workflow_execution_id": parchi.workflow_execution_id,
        "idempotency_key": parchi.idempotency_key,
    }


def _order_dict(order: StandingOrder, *, now: datetime) -> dict[str, Any]:
    return {
        "standing_order_id": order.standing_order_id,
        "site_id": order.site_id,
        "supervisor_id": order.supervisor_id,
        "trigger": {
            "stage": order.trigger.stage,
            "match": order.trigger.match.value,
            "type": order.trigger.type.value,
        },
        "actions": [
            {"action": clause.action.value, "parameters": dict(clause.parameters)}
            for clause in order.actions
        ],
        "valid_from": order.valid_from.isoformat(),
        "valid_until": order.valid_until.isoformat(),
        "status": order.status.value,
        "projected_status": project_status(order, now=now).value,
        "created_at": order.created_at.isoformat(),
        "signed_at": order.signed_at.isoformat() if order.signed_at else None,
        "commitment_hash": order.commitment_hash,
        "trigger_fingerprint": order.trigger_fingerprint,
    }


def _principal(role: str) -> Principal:
    if role == "supervisor":
        return Principal(principal_id=SUPERVISOR_ID, role="supervisor", assigned_site=SITE_ID)
    return Principal(principal_id=FACILITATOR_ID, role="facilitator")


def _denial_sentence(exc: AuthorizationDenied) -> dict[str, Any]:
    """A denial is a sentence to show a user, with the policy that produced it."""
    decision = exc.decision
    return {
        "allowed": False,
        "policy_id": getattr(decision, "policy_id", None),
        "reason": getattr(decision, "reason", str(exc)),
    }


# ---------------------------------------------------------------------------
# Demo state
# ---------------------------------------------------------------------------


class Demo:
    """In-memory demonstration state over the real deterministic core."""

    def __init__(self, corpus_root: Path = DEFAULT_CORPUS) -> None:
        self.corpus_root = Path(corpus_root)
        self._lock = threading.RLock()
        self.site = ConstructionSite.from_dict(json.loads(SITE_FIXTURE.read_text(encoding="utf-8")))
        self.roster = Roster(
            site_id=SITE_ID,
            entries=tuple(
                RosterEntry(worker_id=f"worker-{i:03d}", display_name=f"Worker {i:03d}")
                for i in range(1, WORKER_COUNT + 1)
            ),
        )
        self.registered = {f"worker-{i:03d}" for i in range(1, REGISTERED_WORKERS + 1)}
        self.store = InMemoryParchiStore()
        self.tokens = InMemoryAcknowledgementTokenStore()
        self.ledger = InMemoryIdempotencyLedger()
        self.audit = RecordingAuditLog()
        self.authz = CedarAuthorizationProvider(
            policy_path=CEDAR_DIR / "policies.cedar",
            denials_path=CEDAR_DIR / "denials.json",
            schema_path=CEDAR_DIR / "schema.cedarschema.json",
        )
        self.authz_service = AuthorizationService(authz=self.authz)
        self.order: StandingOrder | None = None
        self._payloads: dict[str, str] = {}
        self._opened = False

    # -- resolution ---------------------------------------------------------

    def _reading(self, key: str) -> StationReading | None:
        path = OBSERVATIONS.get(key)
        if path is None:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StationReading(
            station_id=payload["station_id"],
            parameter=payload["parameter"],
            value=payload["value"],
            observed_at=datetime.fromisoformat(payload["observed_at"]),
            ingested_at=datetime.fromisoformat(payload["ingested_at"]),
            provenance=Provenance(payload["provenance"]),
        )

    def resolve(self, *, scenario: str = "replay", reading: str = "aligned") -> ResolutionResult:
        replay = None
        if scenario == "replay":
            replay = ReplayContext(
                invocation_date=REPLAY_INVOCATION_DATE,
                revocation_date=REPLAY_REVOCATION_DATE,
            )
        return resolve_obligations(
            site=self.site,
            corpus=LocalFileCorpus(self.corpus_root).snapshot(),
            now=datetime.now(UTC),
            replay=replay,
            reading=self._reading(reading),
        )

    def supervisor(self, *, scenario: str = "replay", reading: str = "aligned") -> dict[str, Any]:
        result = self.resolve(scenario=scenario, reading=reading)
        payload = resolution_to_dict(result)
        # `label` and `issues_parchi` live on the domain object but not in the stable JSON
        # contract, so surface them here rather than editing the core serialisation tests pin.
        corpus_rules = {o.obligation_id: o for o in LocalFileCorpus(self.corpus_root).obligations()}
        for obligation in payload["obligations"]:
            rule = corpus_rules.get(obligation["obligation_id"])
            obligation["label"] = rule.label if rule else obligation["obligation_id"]
            obligation["issues_parchi"] = bool(rule.issues_parchi) if rule else False
            # The resolver prefixes every reason with the replay notice. It is shown once, at
            # the top of the screen; repeating it on every card buries the sentence that
            # actually differs. Keep the untouched string as `reason_full` for the audit view.
            notice = payload.get("replay_notice")
            if notice and obligation["reason"].startswith(notice):
                obligation["reason_full"] = obligation["reason"]
                obligation["reason"] = obligation["reason"][len(notice) :].strip()
        invocation = result.stage
        stage = payload["official_stage"]
        payload["site"] = {
            "site_id": SITE_ID,
            "label": SITE_LABEL,
            "activity_type": self.site.activity_type,
            "project_category": self.site.project_category,
        }
        payload["stage_detail"] = {
            "official_stage": stage,
            "is_replay": result.mode.value == "REPLAY",
            "lifecycle": invocation.lifecycle.value if invocation else None,
            "order_doc_id": invocation.order_doc_id if invocation else None,
            "order_date": invocation.invoked_at.isoformat() if invocation else None,
            "order_short_hash": (invocation.order_sha256 or "")[:8] if invocation else None,
            "revoked_at": (
                invocation.revoked_at.isoformat()
                if invocation is not None and invocation.revoked_at
                else None
            ),
            "discrepancy": result.stage_status.status.value == "DISCREPANCY",
        }
        if result.reading is not None:
            age = datetime.now(UTC) - result.reading.observed_at
            payload["reading"]["age_minutes"] = int(age.total_seconds() // 60)
            payload["reading"]["freshness"] = "FRESH" if age <= MAX_READING_AGE else "STALE"
        payload["standing_order"] = (
            _order_dict(self.order, now=datetime.now(UTC)) if self.order else None
        )
        payload["impact"] = self.impact()
        return payload

    def impact(self) -> dict[str, Any]:
        parchis = self.store.for_site(SITE_ID)
        acknowledged = sum(1 for p in parchis if p.state.value in ("acknowledged", "sealed"))
        return {
            "affected": len(self.roster.active_entries()),
            "documented": len(parchis),
            "acknowledged": acknowledged,
            "sealed": sum(1 for p in parchis if p.state.value == "sealed"),
            "readiness_ready": len(self.registered),
            "readiness_total": len(self.roster.active_entries()),
            "standings": self._worker_standings(),
        }

    # -- public impact aggregation (redacted, no PII) -----------------------

    def public_impact(self, *, current_scenario: bool = False) -> dict[str, Any]:
        """Aggregate operational metrics for the public impact screen.

        This endpoint is deliberately conservative:

        * It exposes counts only, never individual records.
        * It does not expose worker names, ids, qr tokens, parchi ids, or
          per-worker state.
        * It does not infer a halt from a Standing Order, or a halted activity
          from a Parchi existing. Each metric is backed only by what the data
          model records.
        * It carries explicit provenance labels so demo/historical/synthetic
          values can never be mistaken for live measurements.

        The four headline metrics map to the brief:

        1. sites_with_active_standing_orders -- count of sites with an active
           Aadesh Standing Order (here: 0 or 1, because the demo holds one
           site; it is a count, not a claim about halts).
        2. sites_acknowledging_regulated_halts -- sites where at least one
           dust-generating activity is documented as restricted under an
           invoked stage. In the demo this is backed by the Stage III replay
           + the piling site's activity_type being a restricted activity.
        3. dust_activities_halted -- count of applicable obligations that
           issue a Parchi (issues_parchi=True) AND are applicable at the
           current invocation. This is a count of restricted activity
           categories, NOT a claim that they were all in progress.
        4. workers_with_documented_displacement -- workers whose parchi has
           been created (issued). This is documentation of displacement, not
           a verified act of halting, and not an entitlement multiplier.

        When any metric cannot be substantiated it is reported as
        unavailable with a reason, never invented.

        :param current_scenario: when True, resolve in CURRENT mode (no replay).
            Use this when testing the 'no verified invocation at all' path.
            The default (False) uses the replay scenario so the public page can
            show the only data available, clearly labelled as historical.
        """
        with self._lock:
            order = self.order
            parchis = self.store.for_site(SITE_ID)
            result = self.resolve(scenario="current" if current_scenario else "replay")

            # Metric 1: sites with an active Standing Order.
            active_orders = 0
            if order is not None:
                projected = project_status(order, now=datetime.now(UTC))
                if projected.value == "active":
                    active_orders = 1

            # Metric 2: sites acknowledging regulated halts.
            sites_acknowledging = 0
            halt_basis: dict[str, Any] | None = None
            if result.stage is not None:
                applicable_restrictions = tuple(
                    r
                    for r in result.results
                    if r.applicable is True
                    and r.issues_parchi
                    and r.status is not ObligationStatus.UNKNOWN
                )
                if applicable_restrictions:
                    sites_acknowledging = 1
                    halt_basis = {
                        "invoked_stage": result.stage.stage,
                        "invoked_at": result.stage.invoked_at.isoformat(),
                        "lifecycle": result.stage.lifecycle.value,
                        "order_doc_id": result.stage.order_doc_id,
                        "restricted_obligation_count": len(applicable_restrictions),
                        "restricted_obligation_ids": sorted(
                            r.obligation_id for r in applicable_restrictions
                        ),
                    }

            # Metric 3: dust-generating activities halted.
            dust_activities_halted = (
                len(halt_basis["restricted_obligation_ids"]) if halt_basis else 0
            )

            # Metric 4: workers with documented displacement.
            workers_documented = len(parchis)

            # Provenance / data-status labels.
            mode = result.mode.value
            is_replay = mode == "REPLAY"
            reading = result.reading
            reading_provenance = reading.provenance.value if reading is not None else None

            return {
                "mode": mode,
                "is_replay": is_replay,
                "is_current_invocation": result.stage is not None
                and result.stage.lifecycle is InvocationLifecycle.ACTIVE
                and result.stage.revoked_at is None,
                "invocation": (
                    {
                        "stage": result.stage.stage,
                        "invoked_at": result.stage.invoked_at.isoformat(),
                        "order_doc_id": result.stage.order_doc_id,
                        "order_sha256": result.stage.order_sha256,
                        "lifecycle": result.stage.lifecycle.value,
                        "revoked_at": (
                            result.stage.revoked_at.isoformat()
                            if result.stage.revoked_at is not None
                            else None
                        ),
                        "is_current": result.stage.is_current,
                        "describe": result.stage.describe(),
                    }
                    if result.stage is not None
                    else None
                ),
                "reading": (
                    {
                        "station_id": reading.station_id,
                        "parameter": reading.parameter,
                        "value": reading.value,
                        "observed_at": reading.observed_at.isoformat(),
                        "provenance": reading_provenance,
                        "is_synthetic": reading_provenance == "synthetic",
                        "is_measured": reading_provenance == "measured",
                        "is_replay": reading_provenance == "replay",
                    }
                    if reading is not None
                    else None
                ),
                "metrics": {
                    "sites_with_active_standing_orders": {
                        "count": active_orders,
                        "label": "Sites with active Aadesh Standing Orders",
                        "description": (
                            "Sites operating under a signed, time-bounded Aadesh"
                            " Standing Order. A Standing Order is a pre-commitment to"
                            " act if a stage is invoked; it is not itself proof that a"
                            " halt occurred."
                        ),
                        "status": "demo" if active_orders else "unavailable",
                        "status_reason": (
                            "Demonstration value: the shipped demo holds one site with"
                            " one Standing Order. There is no verified current official"
                            " invocation, so the order is a demonstration pre-"
                            "commitment, not evidence of live enforcement."
                            if active_orders
                            else ("No active Standing Order is recorded in the current demo state.")
                        ),
                        "reporting_period": (
                            order.valid_until.isoformat() if order is not None else None
                        ),
                    },
                    "sites_acknowledging_regulated_halts": {
                        "count": sites_acknowledging,
                        "label": "Sites acknowledging regulated halts",
                        "description": (
                            "Sites under a verified invoked GRAP stage with at least"
                            " one applicable dust-generating activity restriction. This"
                            " counts the site-level acknowledgement of the regulatory"
                            " posture, not individual worker actions."
                        ),
                        "status": "demo" if sites_acknowledging else "unavailable",
                        "status_reason": (
                            "Demonstration value: derived from the January 2026 Stage"
                            " III historical replay applied to the demo piling site,"
                            " whose activity_type is a Stage III restricted activity."
                            " This is a replay, not a current invocation."
                            if sites_acknowledging
                            else (
                                "No verified current invocation and no applicable"
                                " Stage III restriction are present."
                            )
                        ),
                        "reporting_period": (
                            result.stage.invoked_at.isoformat()
                            if result.stage is not None
                            else None
                        ),
                    },
                    "dust_activities_halted": {
                        "count": dust_activities_halted,
                        "label": "Dust-generating activities halted",
                        "description": (
                            "Count of Stage III dust-generating C&D activity"
                            " categories that are applicable to this site under the"
                            " invoked stage. This is a count of restricted categories,"
                            " not a claim that each was in progress and then stopped."
                        ),
                        "status": "demo" if dust_activities_halted else "unavailable",
                        "status_reason": (
                            "Demonstration value: the demo piling site's activity_type"
                            " is 'Piling works.', which is one of the Stage III"
                            " restricted activities listed in the cited CAQM schedule."
                            if dust_activities_halted
                            else (
                                "No applicable dust-generating restriction is active"
                                " for the current invocation."
                            )
                        ),
                        "reporting_period": (
                            result.stage.invoked_at.isoformat()
                            if result.stage is not None
                            else None
                        ),
                    },
                    "workers_with_documented_displacement": {
                        "count": workers_documented,
                        "label": "Workers with documented displacement",
                        "description": (
                            "Workers for whom Aadesh has issued a Parchi"
                            " (\u092a\u0930\u094d\u091a\u0940) -- a documented record of"
                            " displacement under the invoked stage. A Parchi is"
                            " documentation, not proof a halt occurred, and not an"
                            " entitlement or payment."
                        ),
                        "status": "demo" if workers_documented else "unavailable",
                        "status_reason": (
                            "Demonstration value: the shipped demo roster documents 34"
                            " workers; Parchis are minted when the Standing Order fires."
                            " This is a demonstration roster, not a measured count of"
                            " affected workers in Delhi-NCR."
                            if workers_documented
                            else ("No Parchis have been issued in the current demo state.")
                        ),
                        "reporting_period": (
                            result.stage.invoked_at.isoformat()
                            if result.stage is not None
                            else None
                        ),
                    },
                },
                "data_note": (
                    "This view reflects the Aadesh demonstration application, not"
                    " verified Delhi-NCR production data. The corpus records a Stage"
                    " III invocation on 16 January 2026 and its revocation on 22"
                    " January 2026; there is no verified current invocation. Counts"
                    " shown here are derived from the demonstration scenario and are"
                    " labelled accordingly."
                ),
                "claim_boundary": (
                    "Aadesh records the execution of environmental restrictions and"
                    " the associated operational impact. It does not independently"
                    " establish that ambient air quality improved as a result of its"
                    " use, and it does not estimate tonnes of emissions avoided."
                ),
            }

    def _worker_standings(self) -> list[dict[str, Any]]:
        by_worker = {p.worker_id: p for p in self.store.for_site(SITE_ID)}
        out: list[dict[str, Any]] = []
        for entry in self.roster.active_entries():
            parchi = by_worker.get(entry.worker_id)
            out.append(
                {
                    "worker_id": entry.worker_id,
                    "display_name": entry.display_name,
                    "registered": entry.worker_id in self.registered,
                    "parchi_id": parchi.parchi_id if parchi else None,
                    "state": parchi.state.value if parchi else None,
                    "has_qr": entry.worker_id in self._payloads,
                }
            )
        return out

    # -- standing order + parchis ------------------------------------------

    def create_standing_order(self, *, scenario: str = "replay") -> dict[str, Any]:
        with self._lock:
            now = datetime.now(UTC)
            # The supervisor must be authorized to halt THIS site. Cedar decides it.
            self.authz_service.require_issue_halt(
                principal=_principal("supervisor"), site_id=SITE_ID, now=now
            )
            result = self.resolve(scenario=scenario)
            order = StandingOrder(
                standing_order_id="so-demo-001",
                site_id=SITE_ID,
                supervisor_id=SUPERVISOR_ID,
                trigger=StageInvocationTrigger(stage=3, match=StageMatch.EXACT),
                actions=(
                    StandingOrderActionClause(action=StandingOrderAction.ISSUE_HALT),
                    StandingOrderActionClause(action=StandingOrderAction.OPEN_PARCHI_PER_WORKER),
                ),
                valid_from=now,
                valid_until=now + timedelta(days=7),
                status=StandingOrderStatus.DRAFT,
                created_at=now,
            )
            order = confirm(order, supervisor_id=SUPERVISOR_ID, now=now)
            order = activate(order, now=now)
            self.order = order
            if not self._opened:
                self._open_parchis(result, now=now)
            return _order_dict(order, now=now)

    def _provenance(self, result: ResolutionResult) -> ParchiProvenance:
        obligations = [r for r in result.results if r.applicable and r.issues_parchi]
        corpus = LocalFileCorpus(self.corpus_root)
        stage = result.stage.stage if result.stage else 0
        refs = sorted(
            {
                o.worker_entitlement_ref
                for o in corpus.obligations()
                if o.worker_entitlement_ref and o.triggers_at_stage <= stage
            }
        )
        return ParchiProvenance(
            stage=result.stage,
            reading=result.reading,
            obligation_ids=tuple(sorted(o.obligation_id for o in obligations)),
            entitlement_refs=tuple(refs),
            readiness_checklist=tuple(sorted(o.label for o in obligations)),
            displaced_worker_days=1,
        )

    def _open_parchis(self, result: ResolutionResult, *, now: datetime) -> None:
        execution = WorkflowExecution(
            execution_id="exec-demo-001",
            site_id=SITE_ID,
            source_event_id="evt-replay-" + (result.stage.order_doc_id if result.stage else "none"),
        )
        issues = create_parchis_for_roster(
            execution=execution,
            roster=self.roster,
            provenance=self._provenance(result),
            idempotency_key="so-demo-001",
            now=now,
            store=self.store,
            tokens=self.tokens,
        )
        for issue in issues:
            if issue.qr is not None:
                self._payloads[issue.parchi.worker_id] = issue.qr.payload
        self._opened = True

    def roster_qr(self, *, scenario: str = "replay") -> dict[str, Any]:
        with self._lock:
            if not self._opened:
                self._open_parchis(self.resolve(scenario=scenario), now=datetime.now(UTC))
            items = []
            for entry in self.roster.active_entries():
                parchi = self.store.get(f"parchi:exec-demo-001:{entry.worker_id}")
                items.append(
                    {
                        "worker_id": entry.worker_id,
                        "display_name": entry.display_name,
                        "registered": entry.worker_id in self.registered,
                        "parchi_id": parchi.parchi_id if parchi else None,
                        "payload": self._payloads.get(entry.worker_id),
                        "state": parchi.state.value if parchi else None,
                    }
                )
            return {"workers": items, "impact": self.impact(), "qr_minted": len(self._payloads)}

    def worker_view(self, payload: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        try:
            view = describe_pending_parchi(
                payload=payload, now=now, store=self.store, tokens=self.tokens
            )
            return {
                "status": "PENDING",
                "parchi_id": view.parchi_id,
                "site_id": view.site_id,
                "worker_id": view.worker_id,
                "state": view.state.value,
                "stage": view.stage,
                "provenance": view.provenance.value if view.provenance else None,
                "cites_measured_data": view.cites_measured_data,
                "obligation_ids": list(view.obligation_ids),
                "entitlement_refs": list(view.entitlement_refs),
                "readiness_checklist": list(view.readiness_checklist),
                "displaced_worker_days": view.displaced_worker_days,
                "source_document_ids": list(view.source_document_ids),
                "source_hashes": list(view.source_hashes),
                "expires_at": view.expires_at.isoformat(),
            }
        except TokenRejected:
            parchi = resolve_parchi_for_payload(
                payload=payload, now=now, store=self.store, tokens=self.tokens
            )
            return {
                "status": "ACKNOWLEDGED" if parchi.acknowledged_at else parchi.state.value.upper(),
                "parchi_id": parchi.parchi_id,
                "site_id": parchi.site_id,
                "worker_id": parchi.worker_id,
                "state": parchi.state.value,
                "stage": parchi.stage.stage if parchi.stage else None,
                "acknowledged_at": (
                    parchi.acknowledged_at.isoformat() if parchi.acknowledged_at else None
                ),
                "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
                "content_hash": parchi.content_hash,
            }

    def acknowledge(self, payload: str, worker_id: str) -> dict[str, Any]:
        """Confirm a parchi AS THE WORKER, through the authorization boundary.

        The worker screen asserts who it is; Cedar then checks that the asserted principal is
        the worker named on the parchi (`resource.worker == principal`), and the domain checks
        it again. This adapter never calls the domain operation directly -- that is the whole
        point of `AuthorizationService`, and a test freezes the set of direct callers.
        """
        with self._lock:
            outcome = self.authz_service.acknowledge_own_parchi(
                principal=Principal(principal_id=worker_id, role="worker"),
                payload=payload,
                now=datetime.now(UTC),
                store=self.store,
                tokens=self.tokens,
                ledger=self.ledger,
                audit=self.audit,
            )
            return {
                "parchi": _parchi_dict(outcome.parchi),
                "already_confirmed": outcome.already_confirmed,
                "event_id": outcome.event.event_id,
                "impact": self.impact(),
            }

    # -- Cedar demonstrations ----------------------------------------------

    def cedar_supervisor_acknowledge(self, worker_id: str) -> dict[str, Any]:
        payload = self._payloads.get(worker_id)
        if payload is None:
            return {
                "attempted": "AcknowledgeOwnParchi",
                "denied": True,
                "allowed": False,
                "reason": "No acknowledgement link exists for that worker yet.",
                "policy_id": None,
            }
        try:
            self.authz_service.acknowledge_own_parchi(
                principal=_principal("supervisor"),
                payload=payload,
                now=datetime.now(UTC),
                store=self.store,
                tokens=self.tokens,
                ledger=self.ledger,
                audit=self.audit,
            )
            return {"attempted": "AcknowledgeOwnParchi", "denied": False, "allowed": True}
        except AuthorizationDenied as exc:
            sentence = _denial_sentence(exc)
            return {"attempted": "AcknowledgeOwnParchi", "denied": True, **sentence}
        except WrongWorker as exc:
            return {
                "attempted": "AcknowledgeOwnParchi",
                "denied": True,
                "allowed": False,
                "policy_id": "domain-identity-rule",
                "reason": exc.message,
            }

    def facilitator(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        worker_id = "worker-001"
        parchi = self.store.get(f"parchi:exec-demo-001:{worker_id}")
        if parchi is None:
            return {"error": "Open the standing order first so a parchi exists."}
        facilitator = _principal("facilitator")

        consent = grant_consent(
            context_id="consent-demo-001",
            parchi_id=parchi.parchi_id,
            worker_id=worker_id,
            facilitator_id=FACILITATOR_ID,
            granted_at=now,
            ttl=timedelta(hours=12),
            actor_worker_id=worker_id,
        )
        allowed = {}
        try:
            decision = self.authz_service.require_assist_claim(
                principal=facilitator, consent=consent, now=now
            )
            view = assist_claim(
                consent=consent,
                parchi=parchi,
                facilitator_id=FACILITATOR_ID,
                now=now,
                audit=self.audit,
            )
            allowed = {
                "attempted": ASSIST_CLAIM,
                "allowed": True,
                "policy_id": decision.policy_id,
                "reason": decision.reason,
                "view": {
                    "context_id": view.context_id,
                    "parchi_id": view.parchi_id,
                    "worker_id": view.worker_id,
                    "site_id": view.site_id,
                    "claim_status": view.claim_status,
                    "consent_status": view.consent_status,
                    "consent_granted_at": view.consent_granted_at,
                    "consent_expires_at": view.consent_expires_at,
                },
            }
        except AuthorizationDenied as exc:
            allowed = {"attempted": ASSIST_CLAIM, **_denial_sentence(exc)}

        view_denial = {}
        try:
            self.authz_service.require_view_parchi(principal=facilitator, parchi=parchi, now=now)
            view_denial = {"attempted": VIEW_PARCHI, "allowed": True}
        except AuthorizationDenied as exc:
            view_denial = {"attempted": VIEW_PARCHI, **_denial_sentence(exc)}

        # A consent that was asked for but never granted authorizes nothing.
        pending = request_assistance(
            context_id="consent-demo-request",
            parchi_id=parchi.parchi_id,
            worker_id=worker_id,
            facilitator_id=FACILITATOR_ID,
            requested_at=now,
            ttl=timedelta(hours=12),
        )
        ungranted = {}
        try:
            self.authz_service.require_assist_claim(principal=facilitator, consent=pending, now=now)
            ungranted = {"attempted": ASSIST_CLAIM, "allowed": True}
        except AuthorizationDenied as exc:
            ungranted = {"attempted": ASSIST_CLAIM, **_denial_sentence(exc)}

        return {
            "worker_id": worker_id,
            "parchi_id": parchi.parchi_id,
            "assistance": allowed,
            "read_attempt": view_denial,
            "ungranted_consent_attempt": ungranted,
        }

    # -- verification -------------------------------------------------------

    def verify(self) -> dict[str, Any]:
        plain_buf = io.StringIO()
        plain = run_verify(corpus_root=self.corpus_root, stream=plain_buf)
        tamper_buf = io.StringIO()
        tampered = run_verify(corpus_root=self.corpus_root, tamper=True, stream=tamper_buf)
        return {
            "verify": {
                "command": "make verify",
                "exit_code": int(plain),
                "passed": int(plain) == 0,
                "output": plain_buf.getvalue(),
            },
            "tamper": {
                "command": "make verify-tamper",
                "exit_code": int(tampered),
                "caught": int(tampered) == 1,
                "output": tamper_buf.getvalue(),
            },
        }

    def health(self) -> dict[str, Any]:
        validation = self.authz.validate()
        return {
            "status": "ok",
            "corpus_root": str(self.corpus_root),
            "site_id": SITE_ID,
            "cedar_actions": sorted(self.authz.known_actions),
            "cedar_policy_errors": validation,
        }


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    demo: Demo  # set by serve()

    def log_message(self, *args: Any) -> None:
        return

    # -- helpers ------------------------------------------------------------

    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def do_OPTIONS(self) -> None:
        self._send(204, {})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            self._route_get(parsed.path, query)
        except (AadeshError, ValueError, KeyError) as exc:
            self._send(400, {"error": type(exc).__name__, "reason": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            self._route_post(parsed.path, self._read_body())
        except (AadeshError, ValueError, KeyError) as exc:
            self._send(400, {"error": type(exc).__name__, "reason": str(exc)})

    # -- routes -------------------------------------------------------------

    def _route_get(self, path: str, query: dict[str, str]) -> None:
        demo = self.demo
        if path == "/api/health":
            self._send(200, demo.health())
        elif path == "/api/supervisor":
            self._send(
                200,
                demo.supervisor(
                    scenario=query.get("scenario", "replay"),
                    reading=query.get("reading", "aligned"),
                ),
            )
        elif path == "/api/roster":
            self._send(200, demo.impact())
        elif path == "/api/roster/qr":
            self._send(200, demo.roster_qr(scenario=query.get("scenario", "replay")))
        elif path == "/api/worker":
            payload = query.get("payload", "")
            self._send(200, demo.worker_view(payload))
        elif path == "/api/facilitator":
            self._send(200, demo.facilitator())
        elif path == "/api/verify":
            self._send(200, demo.verify())
        elif path == "/api/impact":
            self._send(200, demo.public_impact())
        else:
            self._send(404, {"error": "NOT_FOUND", "path": path})

    def _route_post(self, path: str, body: dict[str, Any]) -> None:
        demo = self.demo
        if path == "/api/standing-order":
            order = demo.create_standing_order(scenario=body.get("scenario", "replay"))
            self._send(200, {"standing_order": order, "impact": demo.impact()})
        elif path == "/api/roster/qr":
            self._send(200, demo.roster_qr(scenario=body.get("scenario", "replay")))
        elif path == "/api/worker/acknowledge":
            self._send(
                200,
                demo.acknowledge(str(body.get("payload", "")), str(body.get("worker_id", ""))),
            )
        elif path == "/api/cedar/supervisor-acknowledge":
            self._send(
                200, demo.cedar_supervisor_acknowledge(str(body.get("worker_id", "worker-001")))
            )
        else:
            self._send(404, {"error": "NOT_FOUND", "path": path})


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    demo = Demo()
    handler = type("BoundHandler", (Handler,), {"demo": demo})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Aadesh API listening on http://{host}:{port}  (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aadesh-web", description="Aadesh local JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
