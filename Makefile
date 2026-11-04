.PHONY: install fmt lint type test eval check serve docker

install:
	uv sync --extra anthropic --extra mcp --extra ocr
	uv run pre-commit install

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint:
	uv run ruff format --check src tests
	uv run ruff check src tests

type:
	uv run mypy src

test:
	uv run pytest --cov=zelles

eval:
	uv run zelles eval evals/golden --min-f1 0.9

check: lint type test eval

serve:
	uv run zelles serve --port 8000

docker:
	docker compose up --build
