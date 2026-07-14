.PHONY: install install-dev run test test-cov lint format format-check typecheck check clean

install:
	python -m pip install -U pip
	pip install -e .

install-dev:
	python -m pip install -U pip
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload

test:
	pytest

test-cov:
	pytest --cov=app

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

typecheck:
	mypy app

check: lint format-check typecheck test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete