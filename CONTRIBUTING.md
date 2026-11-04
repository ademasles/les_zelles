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
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `feat(extract): detect Ra,tr on facade tables`.

## Adding a field

1. Add it to `SpecField` and `FIELD_CATALOG` in `domain/spec.py`, with French search terms.
2. Add a validator in `domain/validators.py` if it has a format or a range.
3. Put it in a group in `extraction/llm_extractor.py`, and add rules in `extraction/rules.py` if the wording is regular.
4. Add expectations to a golden case and run `zelles eval`.

## Adding a golden case

Anonymise the CCTP (project name, addresses, people, companies), put it in `evals/golden/<case>/` with an `expected.json`, and record where it comes from and that it may be used. The repository is public, so only commit documents cleared for publication. See [docs/evaluation.md](docs/evaluation.md).
