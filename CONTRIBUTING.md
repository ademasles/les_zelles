# Development guide

This is a proprietary project. External pull requests are not accepted without a prior written agreement; bug reports through issues are welcome.

## Setup

```bash
uv sync --extra anthropic --extra mcp --extra ocr
uv run pre-commit install
make check
```

## Ground rules

- `make check` must pass: ruff (format and lint), mypy strict, pytest, and the eval gate.
- Tests never call the network. Use `zelles.llm.fake.FakeLLM` and `HashEmbedder`, or `respx` for HTTP adapters.
- A change to rules, prompts or verification comes with the `zelles eval` result before and after.
- Keep the domain layer (`zelles.domain`) free of I/O.
- Commits and PR titles follow the conventions below.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): imperative subject`, under 72 characters, ideally about 50. Example: `feat(extract): detect Ra,tr on facade tables`.
- Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `revert`. Scopes follow the packages: `ingest`, `extract`, `llm`, `retrieval`, `graph`, `agent`, `api`, `web`, `storage`, `eval`, plus `deps`, `ci` and `docs`.
- One change per commit. Add a body only when the why is not obvious from the diff.
- Branches are short-lived and named after the change (`feat/rules-precision`, `fix/ollama-timeout`).
- PRs are squash-merged, and the PR title becomes the commit on main, so it follows the same format. The `PR title` check enforces it; the `commit-msg` hook (`uv run pre-commit install`) checks local commits.
- PR descriptions follow the template: Summary, Why, Testing. For a change to rules, prompts or verification, put the `zelles eval` result before and after in Why.

## Adding a field

1. Add it to `SpecField` and `FIELD_CATALOG` in `domain/spec.py`, with French search terms.
2. Add a validator in `domain/validators.py` if it has a format or a range.
3. Put it in a group in `extraction/llm_extractor.py`, and add rules in `extraction/rules.py` if the wording is regular.
4. Add expectations to a golden case and run `zelles eval`.

## Adding a golden case

Anonymise the CCTP (project name, addresses, people, companies), put it in `evals/golden/<case>/` with an `expected.json`, and record where it comes from and that it may be used. The repository is public, so only commit documents cleared for publication. See [docs/evaluation.md](docs/evaluation.md).
