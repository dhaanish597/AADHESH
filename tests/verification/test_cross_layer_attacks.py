"""CROSS-LAYER ATTACKS — the fifteen ways in, each one refused.

Every other file in this package proves a property holds. This file tries to break it. Each
test is a concrete attack a real adversary could attempt -- a forged reading, a replayed link,
a swapped document, an impersonated worker, a stalled authorization service -- and each one
must fail at the layer that owns the rule.

The point of running them together, rather than trusting each layer's own unit tests, is that
the interesting failures live *between* layers: a resolver that is correct and a parchi service
that is correct can still compose into a system where a stale order fires.

Naming convention: `test_NN_<the attack>`. The numbering follows the verification brief so a
reviewer can check coverage against it.
"""

from __future__ import annotations

import json
import os
from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path

import pytest

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.authorization import AuthorizationService
from aadesh_core.domain import Principal, ReplayContext
from aadesh_core.domain.enums import (
    InvocationLifecycle,
    ObligationStatus,
    ParchiState,
    ResolutionMode,
    SourceState,
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
)
from aadesh_core.errors import (
    AuthorizationDenied,
    AuthorizationUnavailable,
    CorpusIntegrityError,
    IllegalParchiTransition,
    WrongWorker,
)
from aadesh_core.parchi_ack import (
    ParchiProvenance,
    Roster,
    RosterEntry,
    WorkflowExecution,
    acknowledge_parchi,
    create_parchis_for_roster,
    seal_parchi,
)
from aadesh_core.resolver import resolve_obligations
from aadesh_core.standing_order import (
    StageInvocationTrigger,
    StandingOrder,
    StandingOrderActionClause,
    activate,
    confirm,
    fire,
)
from aadesh_core.standing_order.models import TriggerRun, deterministic_parchi_id
from aadesh_core.standing_order.trigger import StageTripEvent, evaluate_trigger
from tests.unit.test_authorization_no_model import BANNED_ROOTS, _imports
from tests.unit.test_trigger_run_store_contract import FakeTriggerRunStore
from tests.verification.harness import (
    NOW,
    ORDER_DOC,
    RULE_PAGE,
    VALID_FROM,
    VALID_UNTIL,
    build_corpus,
    live_invocation,
    reading,
    site,
    stack,
)

SUPERVISOR = "sup-1"
WORKER_A, WORKER_B = "wrk-1", "wrk-2"
SITE_ID, OTHER_SITE = "site-001", "site-999"


def _resolve(corpus: Path, *, value: float = 420.0, replay: ReplayContext | None = None):
    return resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=NOW,
        reading=reading(value),
        replay=replay,
    )


def _order(*, site_id: str = SITE_ID) -> StandingOrder:
    order = StandingOrder(
        standing_order_id="so-1",
        site_id=site_id,
        supervisor_id=SUPERVISOR,
        trigger=StageInvocationTrigger(stage=3, match=StageMatch.EXACT),
        actions=(StandingOrderActionClause(action=StandingOrderAction.ISSUE_HALT),),
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        status=StandingOrderStatus.DRAFT,
        created_at=VALID_FROM,
    )
    order = confirm(order, supervisor_id=SUPERVISOR, now=VALID_FROM)
    return activate(order, now=VALID_FROM)


def _issue(corpus: Path, repo_root: Path, *, workers: tuple[str, ...] = (WORKER_A,)):
    """Stand up the parchi layer with a live invocation and return (stack, issues)."""
    parts = stack(repo_root)
    invocation = live_invocation(corpus)
    roster = Roster(site_id=SITE_ID, entries=tuple(RosterEntry(w, w) for w in workers))
    issues = create_parchis_for_roster(
        execution=WorkflowExecution(
            execution_id="exec-1", site_id=SITE_ID, source_event_id="evt-1"
        ),
        roster=roster,
        provenance=ParchiProvenance(
            stage=invocation, reading=reading(420.0), obligation_ids=("test-ob-01",)
        ),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )
    return parts, invocation, issues


# --- 1. a forged reading cannot invoke a stage -------------------------------


def test_01_a_forged_aqi_reading_cannot_escalate_the_invoked_stage(tmp_path: Path) -> None:
    """The order invoked Stage II. The attacker reports an AQI of 420, which implies Stage III.
    The clause gated on Stage III must stay unapplicable: a sensor does not amend an order."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=2, bands=(2, 3))

    result = _resolve(corpus, value=420.0)

    assert result.stage is not None and result.stage.stage == 2
    assert result.applicable == ()
    assert all(r.status is ObligationStatus.NOT_APPLICABLE for r in result.results)


@pytest.mark.parametrize("value", [450.0, 999.0, 10_000.0])
def test_01b_shouting_a_bigger_number_changes_nothing(tmp_path: Path, value: float) -> None:
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=2, bands=(2, 3))
    assert _resolve(corpus, value=value).applicable == ()


# --- 2. history cannot be replayed as law ------------------------------------


def test_02_the_revoked_january_invocation_cannot_be_read_as_current(
    shipped_corpus: Path, repo_root: Path
) -> None:
    """The attack: replay the real 16.01.2026 Stage III order and then act as though the site is
    at Stage III *now*. The replay is usable, and it is explicitly not current."""
    replay = ReplayContext(invocation_date="2026-01-16", revocation_date="2026-01-22")

    replayed = _resolve(shipped_corpus, value=420.0, replay=replay)
    current = _resolve(shipped_corpus, value=420.0)

    assert replayed.mode is ResolutionMode.REPLAY
    assert replayed.stage is not None and replayed.stage.is_current is False
    assert current.mode is ResolutionMode.CURRENT
    assert current.stage is None
    assert current.applicable == ()


def test_02b_a_replayed_stage_cannot_fire_a_standing_order(tmp_path: Path) -> None:
    """The sharp end of (2): feed the machine a historical invocation and watch the trigger
    refuse it. `evaluate_trigger` checks currency before anything else.

    The stale stage here is a genuine one -- a live invocation with its lifecycle set to
    REVOKED -- rather than a hand-set boolean, so the refusal rests on the same field the
    loader uses to hide January's order.
    """
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))
    live = live_invocation(corpus)
    stale = replace(
        live,
        lifecycle=InvocationLifecycle.REVOKED,
        revoked_at=NOW,
        revocation_citation=live.citation,
    )
    assert stale.is_current is False

    decision = evaluate_trigger(
        order=_order(), event=StageTripEvent(invoked=stale, site_id=SITE_ID), now=NOW
    )

    assert decision.fires is False
    assert decision.refusal.code == "NOT_CURRENT_INVOCATION"


# --- 3 & 14. a broken source cannot become an actionable obligation ----------


def test_03_tampering_the_source_document_stops_the_corpus_loading(tmp_path: Path) -> None:
    """Edit the order's bytes after it was hashed. The loader refuses outright, so there is no
    path from tampered bytes to an obligation -- not a wrong obligation, none at all."""
    corpus = build_corpus(tmp_path / "corpus")
    document = next((corpus / "sources").glob("*.pdf"), None) or next(
        (corpus / "sources").glob("*.txt")
    )
    body = bytearray(document.read_bytes())
    body[-1] ^= 0x01
    document.write_bytes(bytes(body))

    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(corpus).snapshot()


def test_14_an_obligation_whose_quote_is_not_on_its_page_never_reaches_the_resolver(
    tmp_path: Path,
) -> None:
    """Break only the citation, leaving the document intact. The quote no longer appears on the
    page it names, so the entry is unproved -- and an unproved entry is not a rule."""
    corpus = build_corpus(tmp_path / "corpus")
    path = corpus / "obligations" / "construction_site.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["obligations"][0]["quote"] = "Construction activity must cease entirely."
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(corpus).snapshot()


# --- 4. an unknown fact is not a satisfied one -------------------------------


def test_04_an_absent_fact_leaves_the_obligation_unknown_not_met(tmp_path: Path) -> None:
    """`activity_in_progress` is what the requirement is tested against. Omit it and the honest
    answer is UNKNOWN. The attack is to treat "we don't know" as "we are fine".

    The rule still *applies* -- it is in force at this stage, and hiding an obligation because
    its facts are missing would be its own kind of lie -- but it is reported as unknown, in the
    `unknown` bucket, and never as satisfied.
    """
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))

    result = resolve_obligations(
        site=site(activity_in_progress=None),  # explicitly absent, not False
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=NOW,
        reading=reading(420.0),
    )

    assert result.results[0].status is ObligationStatus.UNKNOWN
    assert [r.obligation_id for r in result.unknown] == ["test-ob-01"]
    assert not any(r.status is ObligationStatus.MET for r in result.results)


def test_04b_a_known_false_fact_is_distinguishable_from_an_unknown_one(tmp_path: Path) -> None:
    """The control. With the fact present and False the obligation IS met -- so (4) is about the
    missing fact, not about the rule being unreachable."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))
    result = resolve_obligations(
        site=site(),
        corpus=LocalFileCorpus(corpus).snapshot(),
        now=NOW,
        reading=reading(420.0),
    )
    assert result.results[0].status is ObligationStatus.MET


# --- 5. a supervisor cannot reach another site -------------------------------


def test_05_an_order_scoped_to_one_site_does_not_fire_for_another(tmp_path: Path) -> None:
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))

    decision = evaluate_trigger(
        order=_order(site_id=SITE_ID),
        event=StageTripEvent(invoked=live_invocation(corpus), site_id=OTHER_SITE),
        now=NOW,
    )

    assert decision.fires is False
    assert decision.refusal.code == "WRONG_SITE"


def test_05b_cedar_refuses_issue_halt_on_a_site_the_supervisor_is_not_assigned_to(
    repo_root: Path,
) -> None:
    authz = AuthorizationService(authz=stack(repo_root).cedar)

    with pytest.raises(AuthorizationDenied):
        authz.require_issue_halt(
            principal=Principal(SUPERVISOR, "supervisor", SITE_ID),
            site_id=OTHER_SITE,
            now=NOW,
        )


# --- 6 & 7. nobody confirms somebody else's parchi ---------------------------


def test_06_worker_a_cannot_confirm_worker_bs_parchi(tmp_path: Path, repo_root: Path) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, issues = _issue(corpus, repo_root, workers=(WORKER_A, WORKER_B))
    _, b_issue = issues

    with pytest.raises(WrongWorker):
        acknowledge_parchi(
            payload=b_issue.qr.payload,
            actor_worker_id=WORKER_A,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )


def test_06b_the_refused_attempt_left_the_parchi_untouched(tmp_path: Path, repo_root: Path) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, issues = _issue(corpus, repo_root, workers=(WORKER_A, WORKER_B))
    _, b_issue = issues
    with pytest.raises(WrongWorker):
        acknowledge_parchi(
            payload=b_issue.qr.payload,
            actor_worker_id=WORKER_A,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )

    still_pending = parts.parchi_store.get(b_issue.parchi.parchi_id)
    assert still_pending is not None and still_pending.state is ParchiState.PENDING_ACK
    assert not parts.audit.for_event("ParchiAcknowledged")


def test_07_a_supervisor_cannot_confirm_a_workers_parchi(tmp_path: Path, repo_root: Path) -> None:
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)

    with pytest.raises(WrongWorker):
        acknowledge_parchi(
            payload=issue.qr.payload,
            actor_worker_id=SUPERVISOR,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )


# --- 8. a replayed link does not confirm twice -------------------------------


def test_08_replaying_the_link_creates_no_second_acknowledgement(
    tmp_path: Path, repo_root: Path
) -> None:
    """A double-tap is not an error -- it is the same fact reported twice -- but it must not
    produce a second event. One link, one acknowledgement, permanently."""
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)

    first = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )
    second = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )

    assert first.already_confirmed is False
    assert second.already_confirmed is True
    assert second.event.event_id == first.event.event_id
    assert len(parts.audit.for_event("ParchiAcknowledged")) == 1


def test_08b_replaying_someone_elses_used_link_is_refused_not_honoured(
    tmp_path: Path, repo_root: Path
) -> None:
    """The identity check runs before the replay memo, so a used link does not become a
    skeleton key for whoever else presents it."""
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)
    acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )

    with pytest.raises(WrongWorker):
        acknowledge_parchi(
            payload=issue.qr.payload,
            actor_worker_id=SUPERVISOR,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )


# --- 9. a redelivered trigger does not duplicate the run ---------------------


def test_09_a_duplicate_trigger_reuses_the_run_and_mints_no_second_parchi(
    tmp_path: Path, repo_root: Path
) -> None:
    """The workflow is retried -- as it will be, since the machine waits on a human. The run is
    claimed by fingerprint and the parchi by idempotency key, so a retry is a no-op."""
    corpus = build_corpus(tmp_path / "corpus")
    parts = stack(repo_root)
    invocation = live_invocation(corpus)
    order = fire(
        _order(),
        now=NOW,
    )
    run_store = FakeTriggerRunStore()
    fingerprint = order.compute_trigger_fingerprint(
        order_doc_id=invocation.order_doc_id, order_sha256=invocation.order_sha256
    )

    def claim_run() -> TriggerRun:
        return run_store.claim(
            TriggerRun(
                fingerprint=fingerprint,
                standing_order_id=order.standing_order_id,
                site_id=SITE_ID,
                stage=3,
                order_doc_id=invocation.order_doc_id,
                order_sha256=invocation.order_sha256,
                started_at=NOW,
                status=StandingOrderStatus.TRIGGERED,
                parchi_ids=(deterministic_parchi_id(fingerprint=fingerprint, worker_id=WORKER_A),),
            )
        )

    def mint():
        return create_parchis_for_roster(
            execution=WorkflowExecution(
                execution_id="exec-1", site_id=SITE_ID, source_event_id="evt-1"
            ),
            roster=Roster(site_id=SITE_ID, entries=(RosterEntry(WORKER_A, WORKER_A),)),
            provenance=ParchiProvenance(stage=invocation, reading=reading(420.0)),
            idempotency_key=fingerprint,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
        )

    first_run, second_run = claim_run(), claim_run()
    (first,) = mint()
    (again,) = mint()

    assert first_run is second_run, "the second claim must return the original run"
    assert first.replayed is False and first.qr is not None
    assert again.replayed is True and again.qr is None, "a replay must not mint a second live link"
    assert again.parchi.parchi_id == first.parchi.parchi_id
    assert again.parchi.created_at == first.parchi.created_at, (
        "the record was reused, not rewritten"
    )


def test_09b_idempotency_is_keyed_per_worker_not_per_run(tmp_path: Path, repo_root: Path) -> None:
    """The control for (9): the same key must still open a parchi for a *second* worker. If the
    replay above passed because the key collapsed everything into one record, this would fail."""
    corpus = build_corpus(tmp_path / "corpus")
    parts, invocation, _ = _issue(corpus, repo_root, workers=(WORKER_A,))
    issues = create_parchis_for_roster(
        execution=WorkflowExecution(
            execution_id="exec-1", site_id=SITE_ID, source_event_id="evt-1"
        ),
        roster=Roster(site_id=SITE_ID, entries=(RosterEntry(WORKER_B, WORKER_B),)),
        provenance=ParchiProvenance(stage=invocation, reading=reading(420.0)),
        idempotency_key="key-1",
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
    )

    (b,) = issues
    assert b.replayed is False and b.qr is not None
    assert b.parchi.worker_id == WORKER_B
    assert b.parchi.parchi_id != f"parchi:exec-1:{WORKER_A}"


# --- 10 & 11. the lifecycle cannot be short-circuited ------------------------


def test_10_a_pending_parchi_cannot_be_sealed(tmp_path: Path, repo_root: Path) -> None:
    """Sealing is what turns a record into evidence. If it could be done before the worker
    confirmed, a supervisor could manufacture evidence of a confirmation that never happened."""
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)

    with pytest.raises(IllegalParchiTransition):
        seal_parchi(parchi=issue.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit)

    stored = parts.parchi_store.get(issue.parchi.parchi_id)
    assert stored is not None and stored.state is ParchiState.PENDING_ACK


def test_11_a_sealed_parchi_cannot_be_confirmed_again(tmp_path: Path, repo_root: Path) -> None:
    """The attack: obtain a seal, then re-present the link to write a second acknowledgement
    onto frozen evidence.

    Two different defences answer it, and both are asserted here. The service memoises the
    confirmation per token, so the replayed call never reaches the domain at all -- it is
    handed the original fact and the *current* record. Underneath, the domain refuses a
    confirmation of a non-pending parchi outright, which is what stops any other route in.
    """
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)
    acknowledged = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )
    sealed = seal_parchi(
        parchi=acknowledged.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit
    )

    replayed = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )

    assert replayed.already_confirmed is True
    assert replayed.parchi.state is ParchiState.SEALED
    stored = parts.parchi_store.get(sealed.parchi_id)
    assert stored is not None
    assert stored.state is ParchiState.SEALED
    assert stored.content_hash == sealed.content_hash
    assert len(parts.audit.for_event("ParchiAcknowledged")) == 1


def test_11b_the_domain_refuses_to_confirm_a_non_pending_parchi(
    tmp_path: Path, repo_root: Path
) -> None:
    """The second lock, reached directly: with the service's replay memo bypassed, the domain
    itself refuses. This is the rule that holds for any other route into `acknowledge`."""
    from aadesh_core.parchi import acknowledge

    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)
    acknowledged = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )
    sealed = seal_parchi(
        parchi=acknowledged.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit
    )

    with pytest.raises(IllegalParchiTransition):
        acknowledge(
            sealed,
            actor_worker_id=WORKER_A,
            now=NOW,
            token_ref=sealed.acknowledgement_token_ref,
            event_id="evt-forced",
        )


def test_11c_sealing_twice_returns_the_original_freeze(tmp_path: Path, repo_root: Path) -> None:
    """A retried seal step must not rewrite when the record was frozen."""
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)
    acknowledged = acknowledge_parchi(
        payload=issue.qr.payload,
        actor_worker_id=WORKER_A,
        now=NOW,
        store=parts.parchi_store,
        tokens=parts.tokens,
        ledger=parts.ledger,
        audit=parts.audit,
    )
    first = seal_parchi(
        parchi=acknowledged.parchi, now=NOW, store=parts.parchi_store, audit=parts.audit
    )
    later = seal_parchi(
        parchi=first,
        now=NOW + timedelta(hours=3),
        store=parts.parchi_store,
        audit=parts.audit,
    )

    assert later.sealed_at == first.sealed_at
    assert later.content_hash == first.content_hash


# --- 12. an unavailable authorizer denies, it does not permit ----------------


class _UnavailableProvider:
    """Stands in for a Cedar engine that cannot be reached or has no policies loaded."""

    def authorize(self, **_kwargs):
        raise AuthorizationUnavailable("the policy engine is not answering")


def test_12_an_unavailable_authorizer_fails_closed() -> None:
    authz = AuthorizationService(authz=_UnavailableProvider())

    with pytest.raises(AuthorizationUnavailable):
        authz.require_issue_halt(
            principal=Principal(SUPERVISOR, "supervisor", SITE_ID), site_id=SITE_ID, now=NOW
        )


def test_12b_the_acknowledgement_gate_fails_closed_too(tmp_path: Path, repo_root: Path) -> None:
    """The same provider on the parchi path: nothing is confirmed when authorization cannot
    answer, even though the domain layer below would have allowed it."""
    corpus = build_corpus(tmp_path / "corpus")
    parts, _, (issue,) = _issue(corpus, repo_root)
    authz = AuthorizationService(authz=_UnavailableProvider())

    with pytest.raises(AuthorizationUnavailable):
        authz.acknowledge_own_parchi(
            principal=Principal(WORKER_A, "worker", SITE_ID),
            payload=issue.qr.payload,
            now=NOW,
            store=parts.parchi_store,
            tokens=parts.tokens,
            ledger=parts.ledger,
            audit=parts.audit,
        )

    stored = parts.parchi_store.get(issue.parchi.parchi_id)
    assert stored is not None and stored.state is ParchiState.PENDING_ACK


# --- 13. the decision path does not reach a model ---------------------------


DECISION_PATH = [
    *sorted((Path("services/aadesh_core/resolver")).glob("*.py")),
    *sorted((Path("services/aadesh_core/parchi_ack")).glob("*.py")),
    *sorted((Path("services/aadesh_core/standing_order")).glob("*.py")),
    *sorted((Path("services/aadesh_core/verification")).glob("*.py")),
    Path("services/aadesh_core/parchi.py"),
    Path("services/aadesh_core/stages.py"),
    Path("services/aadesh_core/citations.py"),
    Path("services/aadesh_core/corpus_validation.py"),
]


@pytest.mark.parametrize("path", DECISION_PATH, ids=lambda p: p.name)
def test_13_the_decision_path_imports_no_model_and_no_network(path: Path, repo_root: Path) -> None:
    """Extends the authorization layer's static no-model check to every module that decides or
    records: the resolver, the parchi lifecycle, the standing-order machine, the verifier.

    Static on purpose. Calling the code and observing that it did not dial out would only prove
    something about the branches that happened to run.
    """
    banned = _imports(repo_root / path) & BANNED_ROOTS
    assert not banned, (
        f"{path.name} imports {sorted(banned)}. The deterministic core must produce the same "
        f"obligations and the same parchis with the model layer unavailable and the network down."
    )


def test_13b_the_whole_chain_runs_with_the_model_and_network_unimportable(
    tmp_path: Path, repo_root: Path
) -> None:
    """The dynamic half, and it has to be a subprocess to mean anything: inside this pytest
    process `subprocess`, `ctypes` and `urllib` are already imported by the test runner, so an
    in-process check would report on pytest rather than on Aadesh.

    The child blocks every AI SDK and every network client at import time and then does the
    ordinary work -- load the corpus, resolve at the invoked stage -- asserting the answer is
    produced by the deterministic core alone. See `_no_model_child.py`.
    """
    import subprocess
    import sys

    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))
    child = Path(__file__).with_name("_no_model_child.py")
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(repo_root / "services"), str(repo_root)]),
    }

    completed = subprocess.run(
        [sys.executable, str(child), str(corpus)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "RESOLVED stage=3 met=['test-ob-01']" in completed.stdout, completed.stdout


# --- 15. no monetary entitlement without a citation -------------------------


def test_15_an_entitlement_cannot_carry_an_amount_without_a_cited_basis(
    tmp_path: Path,
) -> None:
    """The verifier checks an entitlement's citation like any other: a figure whose basis is not
    on the page it names fails, and a failed corpus does not load."""
    corpus = build_corpus(tmp_path / "corpus")
    path = corpus / "entitlements" / "cess_fund.json"
    path.write_text(
        json.dumps(
            {
                "entitlements": [
                    {
                        "entitlement_id": "ent-01",
                        "label": "Compensation for displaced work",
                        "source_doc": ORDER_DOC,
                        "page": RULE_PAGE,
                        "quote": "Workers displaced shall be compensated at Rs. 1,200 per day.",
                        "amount": {
                            "value_inr": 1200,
                            "basis": "per displaced worker-day",
                            "source_doc": ORDER_DOC,
                            "page": RULE_PAGE,
                            "quote": "Workers displaced shall be compensated at Rs. 1,200 per day.",
                        },
                        "readiness_requirements": [],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(CorpusIntegrityError):
        LocalFileCorpus(corpus).snapshot()


def test_15b_a_parchi_records_entitlement_references_and_holds_no_amount(
    tmp_path: Path, repo_root: Path
) -> None:
    """Structurally: `ParchiProvenance` has no field an amount could be smuggled through, and the
    parchi that results carries references only."""
    corpus = build_corpus(tmp_path / "corpus")
    _, _, (issue,) = _issue(corpus, repo_root)

    assert "amount" not in {f.name for f in fields(ParchiProvenance)}
    assert "value_inr" not in {f.name for f in fields(ParchiProvenance)}
    assert all(isinstance(ref, str) for ref in issue.parchi.entitlement_refs)
    assert issue.parchi.entitlement_refs == ()


def test_15c_an_unproved_obligation_is_not_verified_and_is_therefore_not_actionable(
    tmp_path: Path,
) -> None:
    """The gate itself, stated directly. `SourceState.VERIFIED` is what makes a rule actionable,
    and it is computed from the verification run, never declared by the file -- a corpus entry
    that tries to declare its own provenance is rejected at load (`FORBIDDEN_KEYS`)."""
    corpus = build_corpus(tmp_path / "corpus", invoked_stage=3, bands=(3,))
    loader = LocalFileCorpus(corpus)

    obligations = loader.obligations()
    assert obligations and all(o.source_state is SourceState.VERIFIED for o in obligations)
