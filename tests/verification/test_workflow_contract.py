"""WORKFLOW CONTRACT — what the deployed state machine guarantees, read off the ASL.

`tests/unit/test_asl_matches_core_machine.py` already proves the ASL's state *names* and its
`Next` chain match the pure machine, and that a task token is used. This file asserts the
properties that survive a rename: that the wait is durable rather than a timer, that no path
reaches the seal step without passing the acknowledgement step, and that a failed step is
recorded rather than swallowed.

No Lambda is built or deployed here, deliberately. The brief for this layer is to verify the
*machine contract*; the handlers are a deployment concern that would make these assertions
depend on infrastructure rather than on the graph.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ASL_PATH = REPO_ROOT / "infra" / "stepfunctions" / "standing-order.asl.json"

#: The step that must be on every path to the seal, and the one that must not be skippable.
ACKNOWLEDGEMENT_STEP = "PendingAck"
SEAL_STEP = "SealParchis"


@pytest.fixture(scope="module")
def asl() -> dict:
    return json.loads(ASL_PATH.read_text(encoding="utf-8"))


def _walk(node: dict):
    """Yield every mapping in the ASL tree, so assertions cover nested Map/ItemProcessor states
    and not just the top level. A guarantee that only holds at the top level is not a guarantee:
    the wait lives two levels down."""
    yield node
    for value in node.values():
        if isinstance(value, dict):
            yield from _walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _walk(item)


def _edges(asl: dict) -> dict[str, set[str]]:
    """Every Next and every Catch.Next at the top level: the graph the runner actually follows."""
    edges: dict[str, set[str]] = {}
    for name, state in asl["States"].items():
        targets: set[str] = set()
        if "Next" in state:
            targets.add(state["Next"])
        for catcher in state.get("Catch", []):
            if "Next" in catcher:
                targets.add(catcher["Next"])
        edges[name] = targets
    return edges


def _paths(edges: dict[str, set[str]], start: str, goal: str) -> list[list[str]]:
    """All simple paths from start to goal. The graph is a DAG, so this terminates."""
    found: list[list[str]] = []

    def walk(node: str, trail: list[str], seen: set[str]) -> None:
        if node == goal:
            found.append([*trail, node])
            return
        for nxt in sorted(edges.get(node, ())):
            if nxt not in seen:
                walk(nxt, [*trail, node], seen | {nxt})

    walk(start, [], {start})
    return found


# --- the wait is durable ------------------------------------------------------


def test_the_only_long_wait_is_a_task_token_callback(asl: dict) -> None:
    """The machine waits hours for a worker. That wait must be a callback token, so it survives
    a restart and cannot be lost with a browser tab."""
    waits = [
        state
        for state in _walk(asl)
        if isinstance(state.get("Resource"), str) and "waitForTaskToken" in state["Resource"]
    ]

    assert len(waits) == 1, f"expected exactly one durable wait, found {len(waits)}"
    assert waits[0]["Parameters"]["Payload"]["task_token.$"] == "$$.Task.Token"


def test_no_wait_state_exists_anywhere(asl: dict) -> None:
    """The failure this guards against is a `Wait` state standing in for the acknowledgement: a
    clock that fires whether or not a worker ever confirmed. There is none, and if one is added
    this test is where it is caught."""
    clock_states = [
        state for state in _walk(asl) if state.get("Type") in {"Wait", "WaitForCondition"}
    ]
    assert not clock_states, "the acknowledgement wait must be a task token, never a timer"


def test_the_waiter_is_told_which_parchi_and_which_worker_it_is_waiting_for(asl: dict) -> None:
    """A token with no parchi attached could be resumed against the wrong record."""
    waiter = next(
        state
        for state in _walk(asl)
        if isinstance(state.get("Resource"), str) and "waitForTaskToken" in state["Resource"]
    )
    payload = waiter["Parameters"]["Payload"]

    assert "parchi_id.$" in payload
    assert "worker_id.$" in payload
    assert "site_id.$" in payload


def test_an_unanswered_wait_is_recorded_as_unacknowledged(asl: dict) -> None:
    """The timeout path must say so. A wait that expired and was reported as success is the
    quietest possible way to forge a confirmation."""
    timeout = asl["States"]["PendingAck"]["Iterator"]["States"]["AckTimeout"]

    assert timeout["Result"]["acknowledged"] is False
    assert "reason" in timeout["Result"]


# --- the acknowledgement cannot be bypassed ----------------------------------


def test_every_path_to_the_seal_passes_through_the_acknowledgement(asl: dict) -> None:
    """The load-bearing structural claim: there is no route from the start of the machine to
    `SealParchis` that skips `PendingAck`. Checked by enumerating the paths rather than by
    reading the JSON and believing it."""
    routes = _paths(_edges(asl), asl["StartAt"], SEAL_STEP)

    assert routes, "no path reaches the seal step at all -- the graph is wrong"
    for route in routes:
        assert ACKNOWLEDGEMENT_STEP in route, (
            f"a route reaches the seal without confirming: {route}"
        )


def test_the_seal_is_reachable_only_from_the_acknowledgement_step(asl: dict) -> None:
    """The stronger, local form: no state other than the acknowledgement step may point at the
    seal. This is what stops a future step being wired straight into sealing."""
    predecessors = {name for name, targets in _edges(asl).items() if SEAL_STEP in targets}

    assert predecessors == {"WorkerAcknowledgements"}, predecessors


def test_nothing_is_sealed_before_the_workers_have_been_asked(asl: dict) -> None:
    """Ordering, stated once more in terms of the chain: the seal step sits after the Map that
    holds the wait, not before it."""
    chain: list[str] = []
    current = asl["StartAt"]
    while current not in chain:
        chain.append(current)
        state = asl["States"][current]
        if state.get("End") is True or "Next" not in state:
            break
        current = state["Next"]

    assert chain.index(ACKNOWLEDGEMENT_STEP) < chain.index(SEAL_STEP)


# --- failures are recorded, not swallowed ------------------------------------


def test_every_step_that_can_fail_routes_the_failure_to_the_audit_step(asl: dict) -> None:
    """A machine whose failure path is silence produces no evidence of the failure. Every task
    except the audit step itself must catch and hand off to Audit."""
    offenders = [
        name
        for name, state in asl["States"].items()
        if state["Type"] == "Task" and name != "Audit" and not state.get("Catch")
    ]
    assert not offenders, f"these steps can fail without recording it: {offenders}"


def test_the_audit_step_is_terminal_and_cannot_fail_open(asl: dict) -> None:
    audit = asl["States"]["Audit"]

    assert audit["End"] is True
    assert not audit.get("Catch"), "the audit step must not be able to hand off a failure"
    assert audit.get("Retry") == [], "an audit write that retries is fine; one that swallows is not"


def test_the_audit_step_is_the_terminus_of_the_successful_run(asl: dict) -> None:
    """Every successful route ends at Audit -- there is no second exit that skips the record."""
    terminals = {
        name
        for name, state in asl["States"].items()
        if state.get("End") is True and not state.get("Catch")
    }
    assert terminals == {"Audit"}, terminals


# --- the known defect in the Map state ---------------------------------------


def test_the_map_processor_declares_exactly_one_of_iterator_or_itemprocessor(asl: dict) -> None:
    pending = asl["States"]["PendingAck"]

    # A valid Map state declares exactly one processing mode: Iterator (classic) or
    # ItemProcessor (awl/lambda). Declaring both is invalid and the waiter is unreachable.
    assert ("Iterator" in pending) != ("ItemProcessor" in pending), (
        "PendingAck must declare exactly one of Iterator or ItemProcessor, not both and not neither"
    )

    if "Iterator" in pending:
        processor = pending["Iterator"]["States"]
        start = pending["Iterator"]["StartAt"]
    else:
        processor = pending["ItemProcessor"]["States"]
        start = pending["ItemProcessor"]["StartAt"]

    assert start in processor, f"{start!r} is not a state in the processor"
    for name, state in processor.items():
        if "Next" in state:
            assert state["Next"] in processor, (
                f"{name}.Next targets {state['Next']!r}, which is not in the processor"
            )
