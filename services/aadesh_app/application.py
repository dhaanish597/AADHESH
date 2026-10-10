"""`AadeshApplication` -- the one place the demo's behaviour is written down.

Before this module existed the same logic lived twice: once in the local `http.server` skin
and once, more ambitiously and less correctly, in the Lambda adapters. This is that logic,
moved here and stripped of every concrete dependency. It holds ports, not clients:

  * it never imports boto3, never opens a socket, and never reads a file it was not handed;
  * the corpus, the stores, the authorizer and the audit sink all arrive through the
    constructor;
  * the two HTTP skins (local `http.server`, API Gateway) differ only in how they parse a
    request and serialise a reply.

Everything decision-shaped still happens in `aadesh_core`: this class resolves, authorizes,
opens parchis and serialises, and adds no rule of its own.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from aadesh_core.authorization import AuthorizationService
from aadesh_core.authorization.service import ASSIST_CLAIM, VIEW_PARCHI
from aadesh_core.consent import ClaimAssistanceContext, grant_consent, request_assistance
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
from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
)
from aadesh_core.errors import AuthorizationDenied, TokenRejected, WrongWorker
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    Roster,
    WorkflowExecution,
    assist_claim,
    create_parchis_for_roster,
    describe_pending_parchi,
)
from aadesh_core.parchi_ack.service import resolve_parchi_for_payload
from aadesh_core.ports.audit import AuditLog
from aadesh_core.resolver import resolution_to_dict, resolve_obligations
from aadesh_core.standing_order import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    activate,
    confirm,
    project_status,
)

MAX_READING_AGE = timedelta(minutes=90)
CONSENT_TTL = timedelta(hours=12)
ORDER_VALIDITY = timedelta(days=7)


class Corpus(Protocol):
    """The three corpus ports, as one object. `LocalFileCorpus` and `S3Corpus` both satisfy it."""

    def snapshot(self) -> Any: ...
    def obligations(self) -> tuple[Any, ...]: ...
    def entitlements(self) -> tuple[Any, ...]: ...
    def stage_bands(self) -> tuple[Any, ...]: ...
    def documents(self) -> tuple[Any, ...]: ...
    def invoked_stage(self) -> Any: ...
    def invocation_history(self) -> tuple[Any, ...]: ...


class QrLinkCache(Protocol):
    def put(self, *, parchi_id: str, payload: str, expires_at: datetime) -> None: ...
    def get(self, *, parchi_id: str) -> str | None: ...


# ---------------------------------------------------------------------------
# Serialisation helpers (presentation only; no decisions are made here)
# ---------------------------------------------------------------------------


def citation_dict(citation: Any) -> dict[str, Any] | None:
    if citation is None:
        return None
    return {
        "source_doc": citation.source_doc,
        "source_page": citation.page,
        "source_quote": citation.quote,
        "source_hash": citation.source_hash,
        "short_hash": (citation.source_hash or "")[:8],
    }


def parchi_dict(parchi: Parchi) -> dict[str, Any]:
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


def order_dict(order: StandingOrder, *, now: datetime) -> dict[str, Any]:
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


def denial_sentence(exc: AuthorizationDenied) -> dict[str, Any]:
    """A denial is a sentence to show a user, with the policy that produced it."""
    decision = exc.decision
    return {
        "allowed": False,
        "policy_id": getattr(decision, "policy_id", None),
        "reason": getattr(decision, "reason", str(exc)),
    }


class AadeshApplication:
    """The deterministic behaviour, against injected ports.

    State that is genuinely per-request lives on the instance; state that must survive an
    invocation lives behind the stores. The distinction is explicit in `_current_order` and
    `_payload_for`, which are the only two places the local in-memory skin and the DynamoDB
    skin differ.
    """

    def __init__(
        self,
        *,
        site: ConstructionSite,
        roster: Roster,
        registered: set[str] | frozenset[str],
        store: Any,
        tokens: Any,
        ledger: Any,
        authz: Any,
        corpus: Callable[[], Corpus],
        audit: AuditLog,
        site_id: str,
        site_label: str,
        supervisor_id: str,
        facilitator_id: str,
        corpus_root: Path,
        verify_runner: Callable[..., Any] | None = None,
        order_store: Any = None,
        trigger_runs: Any = None,
        task_tokens: Any = None,
        qr_cache: QrLinkCache | None = None,
        readings_store: Any = None,
        explanation_model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.site = site
        self.roster = roster
        self.registered = set(registered)
        self.store = store
        self.tokens = tokens
        self.ledger = ledger
        self.authz = authz
        self.authz_service = AuthorizationService(authz=authz)
        self.audit = audit
        self.site_id = site_id
        self.site_label = site_label
        self.supervisor_id = supervisor_id
        self.facilitator_id = facilitator_id
        self.corpus_root = Path(corpus_root)
        self._corpus = corpus
        self._verify_runner = verify_runner
        self._order_store = order_store
        self._trigger_runs = trigger_runs
        self._task_tokens = task_tokens
        self._qr_cache = qr_cache
        self._readings_store = readings_store
        self._explanation_model_factory = explanation_model_factory
        self._order: StandingOrder | None = None
        self._payloads: dict[str, str] = {}
        self._opened = False

    # -- authorized principals ---------------------------------------------

    def principal(self, role: str) -> Principal:
        if role == "supervisor":
            return Principal(
                principal_id=self.supervisor_id, role="supervisor", assigned_site=self.site_id
            )
        if role == "facilitator":
            return Principal(principal_id=self.facilitator_id, role="facilitator")
        return Principal(principal_id=role, role="worker")

    # -- resolution ---------------------------------------------------------

    def _reading(self, key: str) -> StationReading | None:
        if key != "aligned" and key != "divergent":
            return None
        value = 285.0 if key == "aligned" else 180.0
        return StationReading(
            station_id="DL-NCR-ROHINI-01",
            parameter="PM2.5",
            value=value,
            observed_at=datetime(2026, 1, 16, 8, 0, 0, tzinfo=UTC),
            ingested_at=datetime(2026, 1, 16, 8, 5, 0, tzinfo=UTC),
            provenance=Provenance.SYNTHETIC,
        )

    def resolve(self, *, scenario: str = "replay", reading: str = "aligned") -> ResolutionResult:
        replay = None
        if scenario == "replay":
            replay = ReplayContext(invocation_date="2026-01-16", revocation_date="2026-01-22")
        return resolve_obligations(
            site=self.site.to_profile(),
            corpus=self._corpus().snapshot(),
            now=datetime.now(UTC),
            replay=replay,
            reading=self._reading(reading),
        )

    def supervisor(
        self,
        *,
        scenario: str = "replay",
        reading: str = "aligned",
        principal: Principal | None = None,
    ) -> dict[str, Any]:
        who = principal or self.principal("supervisor")
        self.authz_service.require_view_site_execution(
            principal=who, site_id=self.site_id, now=datetime.now(UTC)
        )
        result = self.resolve(scenario=scenario, reading=reading)
        payload = resolution_to_dict(result)

        corpus_rules = {o.obligation_id: o for o in self._corpus().obligations()}
        for obligation in payload["obligations"]:
            rule = corpus_rules.get(obligation["obligation_id"])
            obligation["label"] = rule.label if rule else obligation["obligation_id"]
            obligation["issues_parchi"] = bool(rule.issues_parchi) if rule else False
            notice = payload.get("replay_notice")
            if notice and obligation["reason"].startswith(notice):
                obligation["reason_full"] = obligation["reason"]
                obligation["reason"] = obligation["reason"][len(notice) :].strip()

        invocation = result.stage
        payload["site"] = {
            "site_id": self.site_id,
            "label": self.site_label,
            "activity_type": self.site.activity_type,
            "project_category": self.site.project_category,
        }
        payload["stage_detail"] = {
            "official_stage": payload["official_stage"],
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
        order = self._current_order()
        payload["standing_order"] = order_dict(order, now=datetime.now(UTC)) if order else None
        payload["impact"] = self.impact()
        return payload

    def _current_order(self) -> StandingOrder | None:
        if self._order is not None:
            return self._order
        if self._order_store is not None:
            orders: Sequence[StandingOrder] = self._order_store.for_site(self.site_id)
            self._order = orders[-1] if orders else None
        return self._order

    def impact(self) -> dict[str, Any]:
        parchis = self.store.for_site(self.site_id)
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

    def public_impact(self, *, current_scenario: bool = False) -> dict[str, Any]:
        """Aggregate operational metrics for the public impact screen.

        Counts only, never individual records; no worker names, ids, qr tokens or parchi ids.
        Each metric is backed only by what the data model records, and carries an explicit
        status and a reason so a demo value can never be mistaken for a measured one.
        """
        order = self._current_order()
        parchis = self.store.for_site(self.site_id)
        result = self.resolve(scenario="current" if current_scenario else "replay")

        active_orders = 0
        if order is not None and project_status(order, now=datetime.now(UTC)).value == "active":
            active_orders = 1

        sites_acknowledging = 0
        restricted_ids: list[str] = []
        if result.stage is not None:
            applicable = tuple(
                r
                for r in result.results
                if r.applicable is True
                and r.issues_parchi
                and r.status is not ObligationStatus.UNKNOWN
            )
            if applicable:
                sites_acknowledging = 1
                restricted_ids = sorted(r.obligation_id for r in applicable)

        workers_documented = len(parchis)
        mode = result.mode.value
        reading = result.reading
        reading_provenance = reading.provenance.value if reading is not None else None

        def metric(
            count: int, label: str, description: str, reason: str, period: str | None
        ) -> dict[str, Any]:
            return {
                "count": count,
                "label": label,
                "description": description,
                "status": "demo" if count else "unavailable",
                "status_reason": reason
                if count
                else "No record in the current demonstration state backs this metric.",
                "reporting_period": period,
            }

        period = result.stage.invoked_at.isoformat() if result.stage is not None else None
        return {
            "mode": mode,
            "is_replay": mode == "REPLAY",
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
                "sites_with_active_standing_orders": metric(
                    active_orders,
                    "Sites with active Aadesh Standing Orders",
                    "Sites operating under a signed, time-bounded Standing Order. A Standing "
                    "Order is a pre-commitment to act if a stage is invoked; it is not itself "
                    "proof that a halt occurred.",
                    "Demonstration value: the demo holds one site with one Standing Order. "
                    "There is no verified current official invocation, so the order is a "
                    "demonstration pre-commitment, not evidence of live enforcement.",
                    order.valid_until.isoformat() if order is not None else None,
                ),
                "sites_acknowledging_regulated_halts": metric(
                    sites_acknowledging,
                    "Sites acknowledging regulated halts",
                    "Sites under a verified invoked GRAP stage with at least one applicable "
                    "dust-generating activity restriction.",
                    "Demonstration value: derived from the January 2026 Stage III historical "
                    "replay applied to the demo piling site. This is a replay, not a current "
                    "invocation.",
                    period,
                ),
                "dust_activities_halted": metric(
                    len(restricted_ids),
                    "Dust-generating activities halted",
                    "Count of Stage III dust-generating C&D activity categories applicable to "
                    "this site under the invoked stage. A count of restricted categories, not "
                    "a claim each was in progress and then stopped.",
                    "Demonstration value: the demo piling site's activity_type is one of the "
                    "Stage III restricted activities listed in the cited CAQM schedule.",
                    period,
                ),
                "workers_with_documented_displacement": metric(
                    workers_documented,
                    "Workers with documented displacement",
                    "Workers for whom Aadesh has issued a Parchi (\\u092a\\u0930\\u094d\\u091a"
                    "\\u0940) -- a documented record of displacement under the invoked stage. "
                    "Documentation, not proof a halt occurred, and not an entitlement.",
                    "Demonstration value: the shipped demo roster documents 34 workers; "
                    "Parchis are minted when the Standing Order fires. This is a demonstration "
                    "roster, not a measured count of affected workers in Delhi-NCR.",
                    period,
                ),
            },
            "data_note": (
                "This view reflects the Aadesh demonstration application, not verified "
                "Delhi-NCR production data. The corpus records a Stage III invocation on 16 "
                "January 2026 and its revocation on 22 January 2026; there is no verified "
                "current invocation. Counts shown here are derived from the demonstration "
                "scenario and are labelled accordingly."
            ),
            "claim_boundary": (
                "Aadesh records the execution of environmental restrictions and the associated "
                "operational impact. It does not independently establish that ambient air "
                "quality improved as a result of its use, and it does not estimate tonnes of "
                "emissions avoided."
            ),
        }

    def _worker_standings(self) -> list[dict[str, Any]]:
        by_worker = {p.worker_id: p for p in self.store.for_site(self.site_id)}
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
                    "has_qr": self._payload_for(entry.worker_id, parchi) is not None,
                }
            )
        return out

    # -- standing order + parchis ------------------------------------------

    def create_standing_order(
        self, *, scenario: str = "replay", principal: Principal | None = None
    ) -> StandingOrder:
        now = datetime.now(UTC)
        who = principal or self.principal("supervisor")
        # The supervisor must be authorized to halt THIS site. Cedar decides it, against the
        # AUTHENTICATED principal's own assignment -- not against a configured default.
        self.authz_service.require_issue_halt(principal=who, site_id=self.site_id, now=now)
        order = StandingOrder(
            standing_order_id=f"so-{now.strftime('%Y%m%dT%H%M%S')}-{now.microsecond:06d}",
            site_id=self.site_id,
            supervisor_id=who.principal_id,
            trigger=StageInvocationTrigger(stage=3, match=StageMatch.EXACT),
            actions=(
                StandingOrderActionClause(action=StandingOrderAction.ISSUE_HALT),
                StandingOrderActionClause(action=StandingOrderAction.OPEN_PARCHI_PER_WORKER),
            ),
            valid_from=now,
            valid_until=now + ORDER_VALIDITY,
            status=StandingOrderStatus.DRAFT,
            created_at=now,
        )
        # The principal who signed it is the one who may sign it: `confirm` refuses any other
        # supervisor, and that check is worth keeping. On the local skin `who` is the configured
        # demonstration supervisor, so this is the same id as before; on AWS it is the
        # authenticated supervisor's own stable identity rather than their `sub`, which is what
        # makes a second supervisor able to sign their own order instead of nobody's.
        order = confirm(order, supervisor_id=who.principal_id, now=now)
        order = activate(order, now=now)
        self._order = order
        if self._order_store is not None:
            self._order_store.save(order)
        if not self._opened:
            self.open_parchis(
                scenario=scenario, execution_id=f"exec-{order.standing_order_id}", now=now
            )
        return order

    def standing_order_payload(self) -> dict[str, Any]:
        order = self._current_order()
        return order_dict(order, now=datetime.now(UTC)) if order else None

    def _provenance(self, result: ResolutionResult) -> ParchiProvenance:
        obligations = [r for r in result.results if r.applicable and r.issues_parchi]
        corpus = self._corpus()
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

    def worker_citations(self, obligation_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Return only the verified corpus citations attached to this worker's Parchi."""
        corpus = self._corpus()
        obligations = {item.obligation_id: item for item in corpus.obligations()}
        documents = {item.doc_id: item for item in corpus.documents()}
        citations: list[dict[str, Any]] = []
        for obligation_id in obligation_ids:
            obligation = obligations.get(obligation_id)
            if obligation is None or obligation.source_state.value != "verified":
                continue
            citation = obligation.citation
            document = documents.get(citation.source_doc)
            if document is None or document.sha256 != citation.source_hash:
                continue
            citations.append(
                {
                    "obligation_id": obligation_id,
                    "source_doc": citation.source_doc,
                    "source_title": document.title,
                    "source_page": citation.page,
                    "source_quote": citation.quote,
                    "source_hash": citation.source_hash,
                    "source_url": document.source_url,
                }
            )
        return citations

    def _payload_for(self, worker_id: str, parchi: Parchi | None) -> str | None:
        if worker_id in self._payloads:
            return self._payloads[worker_id]
        if self._qr_cache is not None and parchi is not None:
            return self._qr_cache.get(parchi_id=parchi.parchi_id)
        return None

    def open_parchis(
        self,
        *,
        scenario: str = "replay",
        execution_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Open one Parchi per active roster entry, idempotently, and cache their links.

        Public because the Step Functions creation step calls it too, with the SAME
        `execution_id` the API used. That shared key is what makes the two callers safe: the
        second one finds the first one's parchis instead of minting a second set.
        """
        moment = now or datetime.now(UTC)
        result = self.resolve(scenario=scenario)
        resolved_execution_id = execution_id or (
            f"exec-{self._order.standing_order_id}" if self._order else "exec-standalone"
        )
        execution = WorkflowExecution(
            execution_id=resolved_execution_id,
            site_id=self.site_id,
            source_event_id="evt-replay-" + (result.stage.order_doc_id if result.stage else "none"),
        )
        issues = create_parchis_for_roster(
            execution=execution,
            roster=self.roster,
            provenance=self._provenance(result),
            idempotency_key=execution.execution_id,
            now=moment,
            store=self.store,
            tokens=self.tokens,
        )
        opened: list[dict[str, Any]] = []
        for issue in issues:
            if issue.qr is not None:
                self._payloads[issue.parchi.worker_id] = issue.qr.payload
                if self._qr_cache is not None:
                    self._qr_cache.put(
                        parchi_id=issue.parchi.parchi_id,
                        payload=issue.qr.payload,
                        expires_at=issue.qr.expires_at,
                    )
            opened.append(
                {
                    "parchi_id": issue.parchi.parchi_id,
                    "worker_id": issue.parchi.worker_id,
                    "state": issue.parchi.state.value,
                    "replayed": issue.replayed,
                }
            )
        self._opened = True
        return {
            "execution_id": resolved_execution_id,
            "parchis": opened,
            "obligation_ids": list(self._provenance(result).obligation_ids),
        }

    def latest_reading(self) -> dict[str, Any]:
        """The most recent stored station reading, with its provenance and freshness.

        Reads the readings table when one is installed. This is the ONLY place a measurement
        number enters the product, and it enters as evidence with a label -- never as an input
        to the stage, which comes from a CAQM order.
        """
        reading = None
        if self._readings_store is not None:
            reading = self._readings_store.latest("DL-NCR-ROHINI-01")
        if reading is None:
            return {
                "available": False,
                "reason": (
                    "No stored reading for this station. Aadesh will not present a number it "
                    "cannot attribute."
                ),
            }
        age_seconds = int((datetime.now(UTC) - reading.observed_at).total_seconds())
        return {
            "available": True,
            "station_id": reading.station_id,
            "parameter": reading.parameter,
            "value": reading.value,
            "observed_at": reading.observed_at.isoformat(),
            "ingested_at": reading.ingested_at.isoformat(),
            "provenance": reading.provenance.value,
            "age_seconds": age_seconds,
            "freshness": (
                "FRESH" if age_seconds <= int(MAX_READING_AGE.total_seconds()) else "STALE"
            ),
            "is_measured": reading.provenance is Provenance.MEASURED,
            "note": (
                "A station reading never activates a GRAP stage. The stage comes from a CAQM "
                "order; this number is shown so the reading and the order can be compared."
            ),
        }

    def roster_qr(self, *, scenario: str = "replay") -> dict[str, Any]:
        by_worker = {p.worker_id: p for p in self.store.for_site(self.site_id)}
        items = []
        for entry in self.roster.active_entries():
            parchi = by_worker.get(entry.worker_id)
            items.append(
                {
                    "worker_id": entry.worker_id,
                    "display_name": entry.display_name,
                    "registered": entry.worker_id in self.registered,
                    "parchi_id": parchi.parchi_id if parchi else None,
                    "payload": self._payload_for(entry.worker_id, parchi),
                    "state": parchi.state.value if parchi else None,
                }
            )
        return {
            "workers": items,
            "impact": self.impact(),
            "qr_minted": sum(1 for item in items if item["payload"]),
        }

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
                "site_label": self.site_label,
                "worker_id": view.worker_id,
                "state": view.state.value,
                "stage": view.stage,
                "provenance": view.provenance.value if view.provenance else None,
                "cites_measured_data": view.cites_measured_data,
                "obligation_ids": list(view.obligation_ids),
                "citations": self.worker_citations(view.obligation_ids),
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
                "site_label": self.site_label,
                "worker_id": parchi.worker_id,
                "state": parchi.state.value,
                "stage": parchi.stage.stage if parchi.stage else None,
                "citations": self.worker_citations(parchi.obligation_ids),
                "acknowledged_at": (
                    parchi.acknowledged_at.isoformat() if parchi.acknowledged_at else None
                ),
                "sealed_at": parchi.sealed_at.isoformat() if parchi.sealed_at else None,
                "content_hash": parchi.content_hash,
            }

    def acknowledge(self, payload: str, worker_id: str) -> dict[str, Any]:
        """Confirm a parchi AS THE WORKER, through the authorization boundary.

        The worker screen asserts who it is; Cedar then checks that the asserted principal is
        the worker named on the parchi, and the domain checks it again.
        """
        outcome = self.authz_service.acknowledge_own_parchi(
            principal=Principal(principal_id=worker_id, role="worker"),
            payload=payload,
            now=datetime.now(UTC),
            store=self.store,
            tokens=self.tokens,
            ledger=self.ledger,
            audit=self.audit,
        )
        if self._task_tokens is not None:
            # If a Step Functions execution is parked on this parchi, release it. A missing
            # token is an ordinary condition (the machine may already have timed out).
            token = self._task_tokens.pop(parchi_id=outcome.parchi.parchi_id)
            if token is not None:
                self._resume_execution(token, outcome.parchi)
        return {
            "parchi": parchi_dict(outcome.parchi),
            "already_confirmed": outcome.already_confirmed,
            "event_id": outcome.event.event_id,
            "impact": self.impact(),
        }

    def _resume_execution(self, task_token: str, parchi: Parchi) -> None:
        """Hook point for the AWS skin. A no-op unless a resumer is installed."""
        resumer = getattr(self, "_resumer", None)
        if resumer is not None:
            resumer(task_token, parchi)

    def install_execution_resumer(self, resumer: Callable[[str, Parchi], None]) -> None:
        self._resumer = resumer

    # -- Cedar demonstrations ----------------------------------------------

    def cedar_supervisor_acknowledge(
        self, worker_id: str, *, principal: Principal | None = None
    ) -> dict[str, Any]:
        who = principal or self.principal("supervisor")
        parchis = self.store.for_worker(worker_id)
        payload = None
        for parchi in parchis:
            payload = self._payload_for(worker_id, parchi)
            if payload:
                break
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
                principal=who,
                payload=payload,
                now=datetime.now(UTC),
                store=self.store,
                tokens=self.tokens,
                ledger=self.ledger,
                audit=self.audit,
            )
            return {"attempted": "AcknowledgeOwnParchi", "denied": False, "allowed": True}
        except AuthorizationDenied as exc:
            return {"attempted": "AcknowledgeOwnParchi", "denied": True, **denial_sentence(exc)}
        except WrongWorker as exc:
            return {
                "attempted": "AcknowledgeOwnParchi",
                "denied": True,
                "allowed": False,
                "policy_id": "domain-identity-rule",
                "reason": exc.message,
            }

    def facilitator(self, *, principal: Principal | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        worker_id = "worker-001"
        parchis = self.store.for_worker(worker_id)
        if not parchis:
            return {"error": "Open the standing order first so a parchi exists."}
        parchi = parchis[0]
        facilitator = principal or self.principal("facilitator")

        consent = self._granted_consent(parchi, worker_id, now, facilitator.principal_id)
        allowed: dict[str, Any] = {}
        try:
            decision = self.authz_service.require_assist_claim(
                principal=facilitator, consent=consent, now=now
            )
            view = assist_claim(
                consent=consent,
                parchi=parchi,
                facilitator_id=facilitator.principal_id,
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
            allowed = {"attempted": ASSIST_CLAIM, **denial_sentence(exc)}

        view_denial: dict[str, Any] = {}
        try:
            self.authz_service.require_view_parchi(principal=facilitator, parchi=parchi, now=now)
            view_denial = {"attempted": VIEW_PARCHI, "allowed": True}
        except AuthorizationDenied as exc:
            view_denial = {"attempted": VIEW_PARCHI, **denial_sentence(exc)}

        pending = request_assistance(
            context_id="consent-demo-request",
            parchi_id=parchi.parchi_id,
            worker_id=worker_id,
            facilitator_id=self.facilitator_id,
            requested_at=now,
            ttl=CONSENT_TTL,
        )
        ungranted: dict[str, Any] = {}
        try:
            self.authz_service.require_assist_claim(principal=facilitator, consent=pending, now=now)
            ungranted = {"attempted": ASSIST_CLAIM, "allowed": True}
        except AuthorizationDenied as exc:
            ungranted = {"attempted": ASSIST_CLAIM, **denial_sentence(exc)}

        return {
            "worker_id": worker_id,
            "parchi_id": parchi.parchi_id,
            "assistance": allowed,
            "read_attempt": view_denial,
            "ungranted_consent_attempt": ungranted,
        }

    def _granted_consent(
        self, parchi: Parchi, worker_id: str, now: datetime, facilitator_id: str | None = None
    ) -> ClaimAssistanceContext:
        return grant_consent(
            context_id="consent-demo-001",
            parchi_id=parchi.parchi_id,
            worker_id=worker_id,
            facilitator_id=facilitator_id or self.facilitator_id,
            granted_at=now,
            ttl=CONSENT_TTL,
            actor_worker_id=worker_id,
        )

    def assist(
        self, *, worker_id: str, parchi_id: str, principal: Principal | None = None
    ) -> dict[str, Any]:
        """The facilitator's assist path against a live consent, for the API ``/api/assist``."""
        now = datetime.now(UTC)
        parchi = self.store.get(parchi_id)
        if parchi is None:
            return {"allowed": False, "reason": "Parchi not found."}
        facilitator = principal or self.principal("facilitator")
        consent = self._granted_consent(parchi, worker_id, now, facilitator.principal_id)
        try:
            self.authz_service.require_assist_claim(principal=facilitator, consent=consent, now=now)
            view = assist_claim(
                consent=consent,
                parchi=parchi,
                facilitator_id=facilitator.principal_id,
                now=now,
                audit=self.audit,
            )
            return {
                "allowed": True,
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
            return {"allowed": False, **denial_sentence(exc)}

    # -- verification -------------------------------------------------------

    def verify(self) -> dict[str, Any]:
        if self._verify_runner is None:  # pragma: no cover -- both skins install one
            raise RuntimeError("No verification runner is installed.")
        plain_buf = io.StringIO()
        plain = self._verify_runner(corpus_root=self.corpus_root, stream=plain_buf)
        tamper_buf = io.StringIO()
        tampered = self._verify_runner(corpus_root=self.corpus_root, tamper=True, stream=tamper_buf)
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

    # -- explanation (outside the enforcement path) -------------------------

    def explain(
        self,
        *,
        scenario: str = "replay",
        reading: str = "aligned",
        principal: Principal | None = None,
    ) -> dict[str, Any]:
        """A plain-language restatement of an ALREADY-computed resolution.

        Never a new decision. The ExplanationService computes the deterministic sentence first
        -- that text is the answer and is always correct. A model, when one is configured, may
        only rephrase it, and its output is contract-checked and grounded before it is used.
        Any failure, violation or absence of a model yields the deterministic text with an
        explicit status, so the screen can say which of the two it is showing.
        """
        from aadesh_core.explanation import (
            ExplanationService,
        )

        result = self.resolve(scenario=scenario, reading=reading)
        model = None
        if self._explanation_model_factory is not None:
            try:
                model = self._explanation_model_factory()
            except Exception:
                # A model that cannot be built is the same fact as a model that cannot answer:
                # the deterministic sentence is shown, and the status says so.
                model = None
        service = ExplanationService(
            authorization=self.authz_service, model=model, audit=self.audit
        )
        outcome = service.explain_site(
            principal=principal or self.principal("supervisor"),
            result=result,
            now=datetime.now(UTC),
        )
        return {
            "status": outcome.status.value,
            "is_available": outcome.is_available,
            "explanation_id": outcome.explanation_id,
            "explanation": {
                "text": outcome.explanation.text,
                "source": outcome.explanation.source,
            },
            "deterministic": {
                "text": outcome.deterministic.text,
                "source": outcome.deterministic.source,
            },
            "model": (
                outcome.model_metadata.get("model_id") or type(model).__name__
                if model is not None
                else None
            ),
            "detail": outcome.detail,
            "violations": [v.kind for v in outcome.violations],
            "unsupported": [str(u) for u in outcome.unsupported],
            "note": (
                "The explanation layer is outside the enforcement path: it rephrases a result "
                "the deterministic engine already computed, and never changes it."
            ),
        }

    def health(self) -> dict[str, Any]:
        validation = self.authz.validate()
        return {
            "status": "ok",
            "site_id": self.site_id,
            "cedar_actions": sorted(self.authz.known_actions),
            "cedar_policy_errors": validation,
        }
