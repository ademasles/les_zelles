# GitHub Copilot Prompt - T4.5 Refactor LLM Client

```md
Act as a senior Python/FastAPI engineer, AI architecture reviewer, and pragmatic production-readiness maintainer.

You are working on Analyse-DCE, a FastAPI + Streamlit POC for analysing CCTP/tender documents with RAG.

Before making changes, read `REFRACTOR_DECISIONS.md` and follow its decisions.

Important constraints:
- Do not rewrite the whole application.
- Keep the application runnable after every ticket.
- Preserve local-first development.
- Streamlit remains the POC frontend and must call backend APIs only.
- FastAPI routes must stay thin.
- Business logic belongs in services.
- SQL persistence belongs behind repositories.
- Vector search belongs behind a `VectorStore` interface.
- LLM calls belong behind an `LLMClient` interface.
- Document parsing belongs behind a `DocumentParser` interface.
- Docling is the preferred parser.
- Docling Markdown is used for RAG/chunking.
- Structured parser output is preserved for provenance/citations/future highlighting.
- PyMuPDF and Tesseract are fallbacks.
- FAISS and SQLite can remain for the POC.
- Do not introduce Kubernetes, React, Celery, Qdrant, PostgreSQL, or production infrastructure unless explicitly requested by the ticket.
- Prefer small incremental changes.
- Preserve existing behaviour unless the ticket explicitly changes it.


Implement ticket T4.5: Refactor LLM Client.

## Objective

Move local LLM calls behind an LLMClient interface so Ollama/Mistral remains the POC implementation but can be replaced later.



## Files to inspect first

- `REFRACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/llm/`
- `backend/nlp/qa.py`
- `backend/nlp/summarization.py`

## Tasks

1. Create `backend/app/llm/base.py` with an LLMClient Protocol/base class.
2. Create `backend/app/llm/ollama_client.py` implementing the interface.
3. Read Ollama base URL and model name from settings.
4. Support a simple `generate(prompt: str) -> str` method, with optional timeout/temperature if already used.
5. Move direct Ollama/request logic into the client where safe.
6. Make LLM client easy to mock in tests.
7. Do not call Ollama in unit tests.

## Out of scope

- Do not rewrite unrelated application logic.
- Do not break existing frontend-critical endpoints.
- Do not introduce production infrastructure unless explicitly requested.

## Validation commands

Run from `backend/` unless stated otherwise:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
uvicorn app.main:app --reload
```

## Acceptance criteria

- [ ] `LLMClient` interface exists.
- [ ] `OllamaClient` implementation exists.
- [ ] Model name/base URL come from settings.
- [ ] LLM calls are mockable.
- [ ] Existing tests pass without live Ollama.
```
