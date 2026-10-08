"""INVARIANT: the core explanation path imports no model, no network, and no authority.

Aadesh must be able to produce every user-facing sentence with the model layer completely
unavailable. That is checked behaviourally elsewhere; here it is checked statically, because a
test that watched one code path not dial out would only tell you about that path.

The adapter half is checked the other way: the adapters may reach a model, but must import no
module that could mutate the compliance system. Bedrock and Strands are explanation surfaces,
not action surfaces.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "services" / "aadesh_core"
ADAPTERS = ROOT / "services" / "aadesh_adapters"

EXPLANATION_PATH = [
    CORE / "explanation" / "__init__.py",
    CORE / "explanation" / "contract.py",
    CORE / "explanation" / "context.py",
    CORE / "explanation" / "deterministic.py",
    CORE / "explanation" / "grounding.py",
    CORE / "explanation" / "prompt.py",
    CORE / "explanation" / "response.py",
    CORE / "explanation" / "service.py",
]

ADAPTER_PATH = [
    ADAPTERS / "explain" / "__init__.py",
    ADAPTERS / "explain" / "bedrock.py",
    ADAPTERS / "explain" / "fake.py",
    ADAPTERS / "explain" / "parsing.py",
    ADAPTERS / "explain" / "strands.py",
]

BANNED_ROOTS = {
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
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "boto3",
    "botocore",
    "subprocess",
    "multiprocessing",
    "ctypes",
    "importlib",
}

#: Modules the explanation adapters must never depend on: these mutate compliance state.
MUTATION_MODULES = (
    "aadesh_core.standing_order",
    "aadesh_core.parchi",
    "aadesh_core.parchi_ack",
    "aadesh_core.authorization",
    "aadesh_core.resolver",
    "aadesh_core.verification",
    "aadesh_core.corpus_validation",
)


def _roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def _modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_the_paths_under_test_are_complete():
    on_disk = {p.name for p in (CORE / "explanation").glob("*.py")}
    listed = {p.name for p in EXPLANATION_PATH if p.parent.name == "explanation"}
    assert on_disk == listed, f"explanation modules not covered: {sorted(on_disk - listed)}"
    for path in (*EXPLANATION_PATH, *ADAPTER_PATH):
        assert path.is_file(), f"{path} is missing"


@pytest.mark.parametrize("path", EXPLANATION_PATH, ids=lambda p: p.name)
def test_the_core_explanation_path_imports_nothing_that_could_vary(path):
    banned = _roots(path) & BANNED_ROOTS
    assert not banned, (
        f"{path.name} imports {sorted(banned)}. The core explanation path must work with no "
        f"model, no network and no AWS SDK."
    )


@pytest.mark.parametrize("path", EXPLANATION_PATH, ids=lambda p: p.name)
def test_the_core_explanation_path_does_not_read_a_clock_or_randomness(path):
    source = path.read_text(encoding="utf-8")
    for forbidden in ("datetime.now(", "datetime.utcnow(", "time.time(", "random.", "uuid4("):
        assert forbidden not in source, f"{path.name} uses {forbidden!r}"


def test_the_core_explanation_path_does_not_import_the_adapters():
    offenders = []
    for path in (CORE / "explanation").rglob("*.py"):
        if _roots(path) & {"aadesh_adapters", "aadesh_cli"}:
            offenders.append(path.name)
    assert not offenders, f"core explanation importing adapters: {offenders}"


@pytest.mark.parametrize("path", ADAPTER_PATH, ids=lambda p: p.name)
def test_the_explanation_adapters_import_no_authority_surface(path):
    imported = _modules(path)
    offenders = sorted(
        m for m in imported for bad in MUTATION_MODULES if m == bad or m.startswith(bad + ".")
    )
    assert not offenders, (
        f"{path.name} imports {offenders}. An explanation adapter must never be able to "
        f"mutate compliance state."
    )


def test_the_bedrock_adapter_imports_boto3_lazily():
    source = (ADAPTERS / "explain" / "bedrock.py").read_text(encoding="utf-8")
    assert "import boto3" in source
    for line in source.splitlines():
        assert not line.startswith("import boto3"), "boto3 must be imported inside a function"


def test_the_strands_adapter_imports_strands_lazily():
    source = (ADAPTERS / "explain" / "strands.py").read_text(encoding="utf-8")
    assert "from strands import" in source
    for line in source.splitlines():
        assert not line.startswith("from strands import"), "strands must be imported lazily"


def test_the_fake_model_is_test_only():
    source = (ADAPTERS / "explain" / "fake.py").read_text(encoding="utf-8")
    assert "AADESH_ENV" in source
    assert "TestOnlyComponentInProduction" in source
