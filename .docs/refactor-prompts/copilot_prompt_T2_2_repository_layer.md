# GitHub Copilot Prompt - T2.2 Add Repository Layer

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


Implement ticket T2.2: Add Repository Layer.

## Objective

Add a small explicit repository layer so SQL operations do not leak into route handlers or future services. Keep repositories pragmatic and easy to mock.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/models/*.py`
- `backend/app/database/*.py`

## Tasks

1. Create `backend/app/repositories/` with `__init__.py`.
2. Add repositories: ProjectRepository, DocumentRepository, ProcessingJobRepository, ChunkRepository, QuestionRepository, AnswerRepository, and FeedbackRepository.
3. Use explicit methods rather than an over-generic repository abstraction.
4. Add methods such as create/get/list/update_status/save_chunks/create_answer_with_citations.
5. Keep session handling compatible with the existing database setup.
6. Do not move large business workflows into repositories.
7. Add simple unit tests with a temporary SQLite database if practical, otherwise add import smoke tests.

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

- [ ] `backend/app/repositories/` exists.
- [ ] Repositories expose clear CRUD/query methods needed by later services.
- [ ] Routes do not need to directly query SQLAlchemy for operations covered by repositories.
- [ ] Repositories are small and mockable.
- [ ] Existing tests pass.
```
