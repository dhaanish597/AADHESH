# Aadesh — build, test and verification entrypoints.
#
# Design rule: the DEFAULT path (`make test`, `make verify`) must never require
# Docker, AWS credentials, or a network. Anything that does is opt-in.

VENV := .venv

# Detect the venv layout from the filesystem rather than from $(OS). Git Bash on Windows
# does not reliably surface OS as a make variable, and guessing wrong makes every target
# fail with "No such file or directory". Falls back to whatever `python` is on PATH so the
# error message is a useful one if `make setup` has not been run.
PY := $(firstword $(wildcard $(VENV)/Scripts/python.exe) $(wildcard $(VENV)/bin/python) python)

export PYTHONPATH := services

.DEFAULT_GOAL := help
.PHONY: help setup test test-all test-integration verify verify-tamper verify-index \
        corpus corpus-help resolve lint fmt dev api web clean check

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Create the venv and install dev dependencies (no Docker, no AWS)
	uv venv --python 3.13 $(VENV)
	uv pip install --python $(VENV) -e ".[dev]"
	@echo ""
	@echo "Setup complete. Next: cp .env.example .env && make test && make verify"

# --- tests -----------------------------------------------------------------

test: ## Run offline pytest: deterministic core, verified corpus and test doubles, no Docker
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

# --- corpus (the only sanctioned way in) -----------------------------------

corpus: ## Add to the corpus: make corpus ARGS="ingest --pdf ~/order.pdf --doc-id x --url https://..."
	@test -n "$(ARGS)" || (echo 'Pass ARGS. Examples:'; echo; $(MAKE) --no-print-directory corpus-help; exit 1)
	$(PY) -m aadesh_cli.corpus $(ARGS)

corpus-help: ## Show the corpus CLI subcommands
	@echo '  ingest          make corpus ARGS="ingest --pdf <file> --doc-id <id> --url <official url>"'
	@echo '  obligation      make corpus ARGS="add-obligation --file obligation.json"'
	@echo '  entitlement     make corpus ARGS="add-entitlement --file entitlement.json"'
	@echo '  stage band      make corpus ARGS="add-stage-band --file band.json"'
	@echo '  invoked stage   make corpus ARGS="invoke-stage --stage 3 --doc-id <id> --page 2 --quote <sentence>"'
	@echo ''
	@echo '  Every quote is checked VERBATIM against the page it cites, using the same'
	@echo '  normalisation `make verify` uses. A paraphrase is refused at the door.'

resolve: ## Resolve a site: make resolve ARGS="--site fixtures/sites/piling-site.json"
	$(PY) -m aadesh_cli.resolve $(ARGS)

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

check: lint test ## What CI runs: lint, tests, then the citation gate
	@# `make verify` distinguishes "not ready" (2) from "wrong" (1) on purpose, so CI
	@# accepts an empty corpus and must never accept a bad citation. Do NOT relax this
	@# into `|| true`: that would make the gate decorative, which is the one outcome
	@# this whole project exists to avoid.
	@$(PY) -m aadesh_cli.verify; code=$$?; 	if [ $$code -eq 2 ]; then 	  echo ""; 	  echo "check: lint ok, tests ok, corpus not ready (exit 2) - accepted."; 	elif [ $$code -ne 0 ]; then 	  echo ""; 	  echo "check: FAILED - the citation gate reported exit $$code."; 	  exit $$code; 	fi

# --- dev -------------------------------------------------------------------

api: ## Run the local JSON API over the deterministic core (port 8787)
	$(PY) -m aadesh_web.server --port 8787

web: ## Run the Next.js frontend (port 3000); needs `make api` in another shell
	cd web && npm install && npm run dev

dev: ## How to run both processes
	@echo "Run these in two shells:"
	@echo "  1) make api     # Aadesh JSON API on http://127.0.0.1:8787"
	@echo "  2) make web     # Next.js frontend on http://localhost:3000"

clean: ## Remove caches and scratch artefacts
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov corpus/sources/.tamper-scratch
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
