# GitHub Copilot Prompt - T4.1 Add Embedding Service

```md
Act as a senior Python/FastAPI engineer, AI architecture reviewer, and pragmatic production-readiness maintainer.

You are working on Analyse-DCE, a FastAPI + Streamlit POC for analysing CCTP/tender documents with RAG.

Before making changes, read `REFACTOR_DECISIONS.md` and follow its decisions.

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


Implement ticket T4.1: Add Embedding Service.

## Objective

Centralize embedding model loading and embedding generation behind a small service/module so routes and RAG orchestration do not instantiate embedding models directly.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/rag/embeddings.py`

## Tasks

1. Create or update `backend/app/rag/embeddings.py`.
2. Read embedding model name from `settings.embedding_model`.
3. Provide methods/functions to embed one query and multiple chunks.
4. Return consistent numpy/list formats expected by FAISS.
5. Expose embedding model name/version where possible for traces.
6. Design for testability by allowing model mocking/injection.
7. Do not call external hosted APIs unless current code already does so.
8. Add unit tests with a mocked embedding model.

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

- [ ] Embedding logic is centralized.
- [ ] Model name comes from settings.
- [ ] Service can embed queries and chunks.
- [ ] Unit tests do not load a heavy real model unless explicitly marked.
- [ ] Existing tests pass.
```
