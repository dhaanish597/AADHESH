"""Shared pytest fixtures and the repo-root locator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Every test runs with AADESH_ENV=test. Several guards key off this: notably
# AllowAllTestOnly refuses to construct when it is anything else.
os.environ.setdefault("AADESH_ENV", "test")

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def core_root() -> Path:
    return REPO_ROOT / "services" / "aadesh_core"


@pytest.fixture(scope="session")
def shipped_corpus(repo_root: Path) -> Path:
    """The corpus actually committed to the repo, empty or not."""
    return repo_root / "corpus"


@pytest.fixture(scope="session")
def verified_corpus(shipped_corpus):
    from aadesh_adapters.corpus.local_file import LocalFileCorpus

    return LocalFileCorpus(shipped_corpus).snapshot()
