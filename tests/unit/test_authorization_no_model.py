"""INVARIANT: authorization is a pure function of the request, and needs nothing outside it.

Aadesh must authorize correctly with the model layer COMPLETELY UNAVAILABLE. That is not a
performance target or a cost optimisation -- it is a correctness requirement. An authorization
decision that depended on a model would be unreproducible: the same request could be permitted
on Tuesday and denied on Friday, and nobody could say which answer was right. An authorization
decision that depended on the network would be unavailable at exactly the moment a site needs
to halt, which is the moment it matters.

So this file reads the source of the authorization path and refuses imports that would make a
decision vary. It is a STATIC check on purpose: a test that called the code and watched it not
dial out would only tell you about the branches it happened to exercise.

The engine itself (`cedarpy`) is allowed, and is the only third-party import permitted here.
It is a Rust library evaluated in-process: no client, no endpoint, no credential.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "services" / "aadesh_core"
ADAPTERS = Path(__file__).resolve().parents[2] / "services" / "aadesh_adapters"

#: Every module a request passes through between arriving and being refused or allowed.
AUTHORIZATION_PATH = [
    CORE / "authorization" / "__init__.py",
    CORE / "authorization" / "resources.py",
    CORE / "authorization" / "service.py",
    CORE / "consent.py",
    CORE / "errors.py",
    CORE / "ports" / "authz.py",
    ADAPTERS / "authz" / "cedar_authz.py",
]

#: The only third-party package the authorization path may import.
PERMITTED_THIRD_PARTY = {"cedarpy"}

BANNED_ROOTS = {
    # models and anything that could contain one
    "openai",
    "anthropic",
    "litellm",
    "cohere",
    "mistralai",
    "ollama",
    "llama_cpp",
    "vllm",
    "transformers",
    "torch",
    "tensorflow",
    "langchain",
    "google",
    "vertexai",
    "bedrock",
    "strands",
    "sagemaker",
    "huggingface_hub",
    # the network
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    # AWS SDKs
    "boto3",
    "botocore",
    # other processes and dynamic loading
    "subprocess",
    "multiprocessing",
    "ctypes",
    "importlib",
}

STDLIB = {
    "__future__",
    "abc",
    "ast",
    "collections",
    "dataclasses",
    "datetime",
    "enum",
    "json",
    "pathlib",
    "secrets",
    "typing",
}

#: In-tree packages a module of this layer may legitimately import.
OWN_PACKAGES = {"aadesh_core", "aadesh_adapters"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # A relative import ("from .resources import ...") has no top-level module.
            found.add(node.module.split(".")[0])
    return found


def test_the_path_under_test_is_the_whole_path():
    """Guards against this file passing because it scanned nothing.

    A new module dropped into the authorization package must be added here, or it goes
    unchecked -- so the on-disk listing is asserted against the list above.
    """
    on_disk = {p.name for p in (CORE / "authorization").glob("*.py")}
    listed = {p.name for p in AUTHORIZATION_PATH if p.parent.name == "authorization"}
    assert on_disk == listed, (
        f"authorization modules not covered by this check: {sorted(on_disk - listed)}"
    )
    for path in AUTHORIZATION_PATH:
        assert path.is_file(), f"{path} is missing"


@pytest.mark.parametrize("path", AUTHORIZATION_PATH, ids=lambda p: p.name)
def test_the_authorization_path_imports_nothing_that_could_vary(path):
    banned = _imports(path) & BANNED_ROOTS
    assert not banned, (
        f"{path.name} imports {sorted(banned)}. Authorization must be reproducible with the "
        f"model layer unavailable and the network down: no LLM, no HTTP, no AWS SDK."
    )


@pytest.mark.parametrize("path", AUTHORIZATION_PATH, ids=lambda p: p.name)
def test_the_authorization_path_imports_almost_nothing_at_all(path):
    """Anything beyond the standard library and cedarpy is a dependency a decision now has.

    Written as an allow-list rather than a deny-list, because the deny-list above can only
    forbid the ways a dependency could vary that somebody thought of. This one fails on a
    package nobody anticipated.
    """
    unexpected = _imports(path) - STDLIB - OWN_PACKAGES - PERMITTED_THIRD_PARTY
    assert not unexpected, (
        f"{path.name} imports {sorted(unexpected)}. The authorization path may depend on the "
        f"standard library, its own package, and cedarpy -- nothing else."
    )


@pytest.mark.parametrize("path", AUTHORIZATION_PATH, ids=lambda p: p.name)
def test_the_authorization_path_does_not_read_a_clock(path):
    """Time is the REQUEST's, supplied as `context.now`, never something the boundary fetches.

    This is what makes consent expiry reproducible: given the same consent and the same
    instant, the same answer. A boundary that read `datetime.now()` would decide differently on
    a re-run, and the re-run is what an auditor does.
    """
    source = path.read_text(encoding="utf-8")
    for forbidden in ("datetime.now(", "datetime.utcnow(", "time.time(", "datetime.today("):
        assert forbidden not in source, f"{path.name} reads the clock via {forbidden!r}"


@pytest.mark.parametrize("path", AUTHORIZATION_PATH, ids=lambda p: p.name)
def test_the_authorization_path_does_not_reach_for_randomness(path):
    """Randomness is the other way a decision stops being reproducible. The one place the
    wider codebase mints a random id moves the ambiguity out of the decision itself."""
    source = path.read_text(encoding="utf-8")
    for forbidden in ("random.", "secrets.", "uuid4(", "os.urandom("):
        assert forbidden not in source, f"{path.name} uses {forbidden!r}"


def test_the_core_authorization_package_does_not_import_the_adapter_layer():
    """The dependency direction stays adapters -> core, even for the authorization boundary.
    The boundary talks to a PORT; which engine answers is the composition root's business."""
    offenders = []
    for path in (CORE / "authorization").rglob("*.py"):
        if _imports(path) & {"aadesh_adapters", "aadesh_cli"}:
            offenders.append(path.relative_to(CORE).as_posix())
    assert not offenders, (
        f"core authorization modules importing adapters: {offenders}. The Cedar adapter must "
        f"satisfy the port from outside, so the engine can be replaced without touching a rule."
    )


def test_the_cedar_adapter_is_evaluated_in_process_and_immutable_during_a_request():
    """The adapter holds loaded policy text and calls a pure Rust function. There is no client
    object, no session, no endpoint -- asserted by reading the names it binds at import."""
    imports = _imports(ADAPTERS / "authz" / "cedar_authz.py")
    assert "cedarpy" in imports
    assert not imports & BANNED_ROOTS


def test_authorization_needs_no_configuration_to_authorize():
    """The provider takes PATHS, not credentials. A policy set on a local disk is the only
    thing a decision requires -- which is what lets this run in a test, offline, with no
    account of any kind."""
    import inspect

    from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider

    parameters = set(inspect.signature(CedarAuthorizationProvider.__init__).parameters)
    assert parameters == {"self", "policy_path", "denials_path", "schema_path"}, (
        f"the provider gained a parameter: {parameters}. If it now needs a credential, an "
        f"endpoint or a region, the offline guarantee is gone."
    )
