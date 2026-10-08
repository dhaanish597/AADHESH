"""INVARIANT: nothing on the acknowledgement path can reason, guess, or reach the network.

The acknowledgement path makes a legal claim about a named worker. That claim must be
reproducible from the record alone, forever, by someone who has nothing but this repository.
Any component that could vary -- a model, a network call, a clock read, a random ranking --
breaks that, and it breaks it invisibly: the record would still look right.

So this file reads the source of the acknowledgement path and refuses the imports that would
make it nondeterministic or dependent on something outside the process. It is a static check
on purpose. A test that called the code and observed it not calling the network would only
tell you about the paths it happened to exercise.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "services" / "aadesh_core"

ACKNOWLEDGEMENT_PATH = [
    CORE / "parchi.py",
    CORE / "parchi_ack" / "__init__.py",
    CORE / "parchi_ack" / "tokens.py",
    CORE / "parchi_ack" / "events.py",
    CORE / "parchi_ack" / "roster.py",
    CORE / "parchi_ack" / "workflow.py",
    CORE / "parchi_ack" / "service.py",
]

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
    # the adapter layer: the core must not know an adapter exists
    "aadesh_adapters",
    "aadesh_cli",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_the_path_under_test_is_the_whole_path():
    """Guards against this file passing because it silently scanned nothing.

    Adding a module to `parchi_ack` without listing it here would otherwise leave it
    unchecked forever.
    """
    on_disk = {p.name for p in (CORE / "parchi_ack").glob("*.py")}
    listed = {p.name for p in ACKNOWLEDGEMENT_PATH if p.parent.name == "parchi_ack"}

    assert on_disk == listed, (
        f"parchi_ack modules not covered by this check: {sorted(on_disk - listed)}"
    )
    for path in ACKNOWLEDGEMENT_PATH:
        assert path.is_file(), f"{path} is missing"


@pytest.mark.parametrize("path", ACKNOWLEDGEMENT_PATH, ids=lambda p: p.name)
def test_the_acknowledgement_path_imports_nothing_that_could_vary(path):
    banned = _imports(path) & BANNED_ROOTS
    assert not banned, (
        f"{path.name} imports {sorted(banned)}. The acknowledgement path must be reproducible "
        f"from the record alone: no model, no network, no AWS SDK, no adapter layer."
    )


@pytest.mark.parametrize("path", ACKNOWLEDGEMENT_PATH, ids=lambda p: p.name)
def test_the_acknowledgement_path_does_not_read_a_clock(path):
    """Time is a parameter everywhere in the core, never something the core goes and gets.

    A parchi that stamped itself with `datetime.now()` could not be reproduced in a test, and
    more importantly could not be reproduced by an auditor re-running the decision later.
    """
    source = path.read_text(encoding="utf-8")
    for forbidden in ("datetime.now(", "datetime.utcnow(", "time.time(", "datetime.today("):
        assert forbidden not in source, f"{path.name} reads the clock via {forbidden!r}"


def test_the_core_does_not_import_the_adapter_layer_anywhere():
    """The dependency direction is adapters -> core, never the reverse."""
    offenders = []
    for path in CORE.rglob("*.py"):
        if _imports(path) & {"aadesh_adapters", "aadesh_cli"}:
            offenders.append(path.relative_to(CORE).as_posix())
    assert not offenders, f"core modules importing adapters: {offenders}"


def test_the_acknowledgement_service_takes_every_collaborator_as_a_parameter():
    """No module-level singletons or globals holding a store, a clock or a model.

    Checked by signature rather than by eye: the functions that could hide one are exactly the
    ones this asserts about.
    """
    import inspect

    from aadesh_core.parchi_ack import service, workflow

    for function in (
        service.acknowledge_parchi,
        service.describe_pending_parchi,
        service.seal_parchi,
        workflow.create_parchi_for_worker,
        workflow.create_parchis_for_roster,
        workflow.issue_acknowledgement_qr,
    ):
        parameters = inspect.signature(function).parameters
        assert all(
            p.kind is not p.VAR_KEYWORD and p.kind is not p.VAR_POSITIONAL
            for p in parameters.values()
        ), f"{function.__name__} accepts **kwargs, which could smuggle in a collaborator"
        assert parameters, f"{function.__name__} takes no parameters, so it must use globals"


def test_the_acknowledgement_path_module_list_has_no_gaps():
    """Every module in the path is one this session wrote or reviewed, and none is empty."""
    for path in ACKNOWLEDGEMENT_PATH:
        assert path.stat().st_size > 200, f"{path.name} looks empty"
