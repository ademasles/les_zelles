.DEFAULT_GOAL := help

PYTHON ?= python3
APP ?= app.main:app
PACKAGE ?= app
TEST_PATH ?= tests
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help bootstrap install install-dev run \
	test test-cov lint fix format format-check \
	typecheck check clean

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; \
		{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Upgrade pip
	$(PYTHON) -m pip install --upgrade pip

install: ## Install the application
	$(PYTHON) -m pip install .

install-dev: ## Install the application and development dependencies
	$(PYTHON) -m pip install --editable ".[dev]"

run: ## Run the development server
	$(PYTHON) -m uvicorn $(APP) \
		--reload \
		--host $(HOST) \
		--port $(PORT)

test: ## Run the test suite
	$(PYTHON) -m pytest $(TEST_PATH)

test-cov: ## Run tests with coverage
	$(PYTHON) -m pytest $(TEST_PATH) \
		--cov=$(PACKAGE) \
		--cov-report=term-missing \
		--cov-report=html

lint: ## Check code with Ruff
	$(PYTHON) -m ruff check .

fix: ## Apply safe lint fixes, then format the codebase
	@status=0; \
	$(PYTHON) -m ruff check --fix . || status=$$?; \
	$(PYTHON) -m ruff format . || exit $$?; \
	exit $$status

format: ## Format the codebase
	$(PYTHON) -m ruff format .

format-check: ## Check formatting without modifying files
	$(PYTHON) -m ruff format --check .

typecheck: ## Run static type checking
	$(PYTHON) -m mypy $(PACKAGE)

alembic-upgrade: ## Apply database migrations
	alembic upgrade head

check: lint format-check typecheck test ## Run all quality checks

clean: ## Remove generated files, caches, and build artefacts
	rm -rf \
		.pytest_cache \
		.ruff_cache \
		.mypy_cache \
		htmlcov \
		.coverage \
		coverage.xml \
		build \
		dist
	find . \
		-type d \( \
			-name ".git" \
			-o -name ".venv" \
			-o -name "node_modules" \
		\) -prune \
		-o -type d -name "__pycache__" \
		-exec rm -rf {} +
	find . \
		-type d \( \
			-name ".git" \
			-o -name ".venv" \
			-o -name "node_modules" \
		\) -prune \
		-o -type f \( \
			-name "*.pyc" \
			-o -name "*.pyo" \
		\) -delete