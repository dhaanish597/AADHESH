"""INVARIANT: there is one door, and it is locked; and a failed lock is never an open door.

Two separate properties, checked statically because both are about the SHAPE of the code
rather than the result of running it.

**1. No bypass.** A security boundary that a caller can walk around is decoration. The
concrete failure the brief names is:

    Bad:  CLI -> acknowledge_parchi()        while   HTTP/Lambda -> Cedar -> acknowledge_parchi()

Every route to the domain operation has to pass the authorizer. That cannot be enforced by
convention -- it has to be enforced by there being nowhere else to call from, plus a test that
fails the moment a new caller appears. `test_every_caller_of_the_domain_operation_is_accounted_for`
freezes the set of callers, so adding one is a deliberate act with a test to update rather than
a quiet second entrance.

**2. No fail-open.** The brief forbids `try: cedar_authorize() except: allow()` by name, and
names the right response: an explicit `AuthorizationUnavailable`. This is checked two ways --
that no `except` handler in the service layer can return `True`, and that every handler in the
authorization path ends by raising.

Both checks are AST-based. A grep for `except: allow()` would miss it written as `except
Exception: pass` followed by a permissive default twenty lines later.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[2] / "services"
CORE = SERVICES / "aadesh_core"
ADAPTERS = SERVICES / "aadesh_adapters"

AUTHORIZATION_PATH = [
    CORE / "authorization" / "__init__.py",
    CORE / "authorization" / "resources.py",
    CORE / "authorization" / "service.py",
    CORE / "consent.py",
    CORE / "ports" / "authz.py",
    ADAPTERS / "authz" / "cedar_authz.py",
]

#: The callers permitted to reach `acknowledge_parchi`.
#:
#: `authorization/service.py` is the boundary: authorize, then act.
#: `aadesh_cli/parchi.py` is the Prompt 5 DOMAIN demo, whose module docstring states in its
#: own words that it "is NOT the API" and that authorization "is elsewhere". It exists to show
#: the domain's state machine and its identity rule, deliberately including the refusals -- a
#: demo of a rule has to be able to reach the rule.
#:
#: Production handlers get the boundary, and a new entry here means a new door: it should be
#: argued for in review, not added to make a test pass.
PERMITTED_DOMAIN_CALLERS = {
    "aadesh_core/authorization/service.py",
    "aadesh_cli/parchi.py",
}

DOMAIN_OPERATION = "acknowledge_parchi"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _called_names(path: Path) -> set[str]:
    """Every bare or attribute call target named in the file."""
    names: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _service_modules() -> list[Path]:
    return sorted(p for p in SERVICES.rglob("*.py") if "__pycache__" not in p.parts)


# ---------------------------------------------------------------------------
# 1. No bypass
# ---------------------------------------------------------------------------


def test_every_caller_of_the_domain_operation_is_accounted_for():
    """The set of modules reaching the domain operation, frozen.

    Deliberately an equality rather than a subset check. A new caller must fail this test, and
    the failure is the prompt to ask whether that caller authorizes first -- which is the
    question the whole boundary exists to force.
    """
    callers = {
        path.relative_to(SERVICES).as_posix()
        for path in _service_modules()
        if DOMAIN_OPERATION in _called_names(path)
    }

    assert callers == PERMITTED_DOMAIN_CALLERS, (
        f"unaccounted callers of {DOMAIN_OPERATION}(): "
        f"{sorted(callers - PERMITTED_DOMAIN_CALLERS)}. A new caller is a new door: route it "
        f"through aadesh_core.authorization.AuthorizationService, or add it here with a "
        f"written reason it is safe."
    )


def test_the_boundary_module_is_the_one_that_authorizes_and_then_acts():
    """The permitted non-demo caller must actually BE the boundary -- not merely be listed as
    one. It calls the authorizer and it calls the operation, in that order, in one function."""
    boundary = CORE / "authorization" / "service.py"
    source = boundary.read_text(encoding="utf-8")

    assert "acknowledge_parchi(" in source
    assert "self._authorize(" in source
    assert source.index("self._authorize(") < source.rindex("return acknowledge_parchi("), (
        "the authorization call must precede the domain operation in acknowledge_own_parchi"
    )

    function = next(
        node
        for node in ast.walk(_tree(boundary))
        if isinstance(node, ast.FunctionDef) and node.name == "acknowledge_own_parchi"
    )
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    }
    assert {"_authorize", "acknowledge_parchi"} <= calls, (
        "authorize-then-act must be ONE step inside the boundary, or a caller can perform the "
        "second half without the first"
    )


def test_the_domain_demo_says_in_its_own_words_that_it_is_not_the_boundary():
    """The one exception above is only safe because the module documents it. If that sentence
    is ever removed, the exception has lost its justification and this fails."""
    docstring = ast.get_docstring(_tree(SERVICES / "aadesh_cli" / "parchi.py")) or ""

    assert "NOT the API" in docstring
    assert "Authorization" in docstring


def test_no_module_in_the_core_reaches_past_the_port_to_a_policy_engine():
    """Only the adapter may name Cedar. A core module importing cedarpy would mean a rule had
    escaped the policy set and become Python."""
    offenders = [
        path.relative_to(SERVICES).as_posix()
        for path in CORE.rglob("*.py")
        if "cedarpy" in _called_names(path)
        or any(
            (isinstance(n, ast.Import) and any(a.name.startswith("cedarpy") for a in n.names))
            or (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("cedarpy"))
            for n in ast.walk(_tree(path))
        )
    ]
    assert not offenders, (
        f"core modules reaching into the policy engine: {offenders}. Rules live in "
        f"infra/cedar/policies.cedar, where they can be read and audited as one set."
    )


# ---------------------------------------------------------------------------
# 1b. Authorization logic is not duplicated around the codebase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [p for p in CORE.rglob("*.py") if "__pycache__" not in p.parts])
def test_no_core_module_decides_permission_by_comparing_a_role(path):
    """A `principal.role == "supervisor"` anywhere but the policy set is a second, unaudited
    authorization system -- and the one nobody reviews, because it does not look like policy.

    The core reads roles only to carry them into a request. The comparison happens in Cedar.

    Applied to the authorization package too, deliberately. "The boundary builds requests; it
    does not compare roles" is true today and is exactly the kind of thing that stops being
    true in a hurry -- a convenience `if principal.role == ...` inside the boundary would be the
    most dangerous comparison in the repository, because it would look like the boundary doing
    its job.
    """
    offenders = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for operand in operands:
            if isinstance(operand, ast.Attribute) and operand.attr in {"role", "assigned_site"}:
                offenders.append(f"line {node.lineno}")

    assert not offenders, (
        f"{path.relative_to(SERVICES).as_posix()} compares {offenders}. Permission is decided "
        f"in infra/cedar/policies.cedar against a `role` attribute, not in Python."
    )


# ---------------------------------------------------------------------------
# 2. No fail-open
# ---------------------------------------------------------------------------


def _except_handlers(path: Path) -> list[ast.ExceptHandler]:
    return [n for n in ast.walk(_tree(path)) if isinstance(n, ast.ExceptHandler)]


def _returns_true(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Return):
            value = node.value
            if isinstance(value, ast.Constant) and value.value is True:
                return True
            if isinstance(value, ast.Call) and any(
                kw.arg == "allowed"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in value.keywords
            ):
                return True
    return False


@pytest.mark.parametrize(
    "path", [p for p in SERVICES.rglob("*.py") if "__pycache__" not in p.parts]
)
def test_no_except_handler_in_the_service_layer_can_permit(path):
    """The forbidden shape, in every spelling.

    `try: authorize() except: return True` is the thing the brief prohibits by name. So is
    `except: pass` followed by a permissive default, so is catching an engine fault and
    synthesising `AuthorizationDecision(allowed=True, ...)`. All of them are a `return` of a
    truthy permission inside a handler, and all of them fail here.

    Scanned across the WHOLE service layer rather than just the authorization path, because a
    fail-open is exactly the kind of thing that gets added one layer away from where anyone is
    looking.
    """
    offenders = [
        f"line {handler.lineno}" for handler in _except_handlers(path) if _returns_true(handler)
    ]
    assert not offenders, (
        f"{path.relative_to(SERVICES).as_posix()} returns permission from {offenders}. An "
        f"authorization fault must raise AuthorizationUnavailable, never default to allowed."
    )


@pytest.mark.parametrize("path", AUTHORIZATION_PATH, ids=lambda p: p.name)
def test_every_except_handler_in_the_authorization_path_ends_by_raising(path):
    """Fail closed at the handler level.

    The check above forbids returning permission; this one forbids the softer failure of
    swallowing the fault and carrying on, which leaves the caller holding a decision that was
    never reached. A handler in this path either propagates the original exception (a bare
    `raise`) or raises `AuthorizationUnavailable`.
    """
    handlers = _except_handlers(path)
    for handler in handlers:
        assert handler.body, f"{path.name} has an empty except handler at line {handler.lineno}"
        assert isinstance(handler.body[-1], ast.Raise), (
            f"{path.name} line {handler.lineno}: this except handler does not end by raising. "
            f"An authorization fault that is logged and swallowed becomes a request that "
            f"proceeds with no decision behind it."
        )


def test_the_boundary_has_no_except_clause_at_all_around_authorization():
    """`_authorize` must be transparent: if the provider raises, that exception IS the answer.
    There is no catch here to get wrong, which is the simplest possible way to be correct."""
    boundary = _tree(CORE / "authorization" / "service.py")
    function = next(
        node
        for node in ast.walk(boundary)
        if isinstance(node, ast.FunctionDef) and node.name == "_authorize"
    )
    assert not [n for n in ast.walk(function) if isinstance(n, ast.Try)], (
        "_authorize has grown a try/except. Whatever it now handles, the failure it is hiding "
        "is an authorization outage being reported as something else."
    )


# ---------------------------------------------------------------------------
# The guards themselves are tested
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "try:\n    authorize()\nexcept Exception:\n    return True\n",
        "try:\n    authorize()\nexcept Exception:\n    return AuthorizationDecision("
        "allowed=True, policy_id=None, reason='x')\n",
        "try:\n    authorize()\nexcept Exception as e:\n    if e:\n        return True\n",
    ],
    ids=["bare-true", "decision-allowed-true", "nested"],
)
def test_the_fail_open_check_catches_the_idiom_it_exists_to_forbid(source, tmp_path):
    """A guard nobody has watched fail is a guard nobody knows works.

    The realistic spellings of `try: authorize() except: allow()`, including ones a grep for
    the exact string would walk straight past.
    """
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    assert [h for h in _except_handlers(path) if _returns_true(h)], (
        f"the fail-open check missed:\n{source}"
    )


def test_the_fail_open_check_has_a_known_blind_spot(tmp_path):
    """Pinned deliberately, so it is a documented limit rather than a false confidence.

    A truthy value laundered through a local -- `except: passed = True; return passed` -- is not
    caught. Tracking it needs dataflow analysis, not an AST walk. The check is a tripwire for
    the shape people actually write, not a prover; the real defence against a laundered
    fail-open is that review sees a handler which does not re-raise.
    """
    path = tmp_path / "sample.py"
    path.write_text(
        "def f():\n    try:\n        authorize()\n    except Exception:\n"
        "        passed = True\n        return passed\n",
        encoding="utf-8",
    )
    assert not [h for h in _except_handlers(path) if _returns_true(h)]


def test_the_handler_raise_check_catches_a_swallowed_fault(tmp_path):
    """The softer failure, which the check above does not see: an `except` that neither permits
    nor propagates, leaving the caller with a decision that was never reached."""
    path = tmp_path / "sample.py"
    path.write_text(
        "def f():\n    try:\n        authorize()\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    handlers = _except_handlers(path)
    assert handlers and not isinstance(handlers[0].body[-1], ast.Raise)


def test_the_role_check_catches_a_permission_comparison(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(
        "def f(principal):\n    if principal.role == 'supervisor':\n        return True\n",
        encoding="utf-8",
    )
    found = [
        node
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Compare)
        and any(
            isinstance(o, ast.Attribute) and o.attr in {"role", "assigned_site"}
            for o in [node.left, *node.comparators]
        )
    ]
    assert found
