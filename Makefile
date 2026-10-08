# Aadesh — build, test and verification entrypoints.
#
# Design rule: the DEFAULT path (`make test`, `make verify`) must never require
# Docker, AWS credentials, or a network. Anything that does is opt-in.

VENV := .venv
ifeq ($(OS),Windows_NT)
  PY := $(VENV)/Scripts/python.exe
else
  PY := $(VENV)/bin/python
endif

export PYTHONPATH := services

.DEFAULT_GOAL := help
.PHONY: help setup test test-all test-integration verify verify-tamper verify-index \
        lint fmt dev clean check

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Create the venv and install dev dependencies (no Docker, no AWS)
	uv venv --python 3.13 $(VENV)
	uv pip install --python $(VENV) -e ".[dev]"
	@echo ""
	@echo "Setup complete. Next: cp .env.example .env && make test && make verify"

# --- tests -----------------------------------------------------------------

test: ## Run the default suite: pure pytest, fakes only, no Docker (~seconds)
	$(PY) -m pytest -m "not integration and not requires_index"

test-integration: ## Run the same core against LocalStack (requires Docker)
	$(PY) -m pytest -m integration

test-all: ## Everything, including Docker-dependent suites
	$(PY) -m pytest

# --- verification (the centrepiece) ----------------------------------------

verify: ## Re-prove every citation against hashed source bytes. Zero infra.
	$(PY) -m aadesh_cli.verify

verify-tamper: ## Flip one byte in a scratch copy and prove the check CATCHES it.
	$(PY) -m aadesh_cli.verify --tamper

verify-index: ## Additionally assert the OpenSearch index agrees (requires Docker)
	$(PY) -m aadesh_cli.verify --with-index

# NOTE ON SYNTAX: `make verify --tamper` is NOT valid GNU make — make parses
# `--tamper` as one of its own options and aborts. Use `make verify-tamper`,
# or call the CLI directly: `python -m aadesh_cli.verify --tamper`.

# --- quality ---------------------------------------------------------------

lint: ## Lint without modifying files
	$(PY) -m ruff check services tests
	$(PY) -m ruff format --check services tests

fmt: ## Autoformat and autofix
	$(PY) -m ruff check --fix services tests
	$(PY) -m ruff format services tests

check: lint test verify ## What CI runs

# --- dev -------------------------------------------------------------------

dev: ## Run the local API (same core as Lambda) plus the Next.js dev server
	@echo "Not wired yet - see docs/superpowers/specs/2026-10-08-aadesh-v2-foundation-design.md section 11"

clean: ## Remove caches and scratch artefacts
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov corpus/sources/.tamper-scratch
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
