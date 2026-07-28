# GitHub Copilot Prompt - T2.3 Define File Storage Layout

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


Implement ticket T2.3: Define File Storage Layout.

## Objective

Create a local-first file storage abstraction for raw uploads, parsed Markdown, structured parser JSON, page artifacts, and vector indexes. This prepares the codebase for Docling output persistence without coupling parsing to filesystem paths.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/storage/`
- `.env.example`

## Tasks

1. Create `backend/app/storage/paths.py` and `backend/app/storage/file_store.py`.
2. Use `settings.storage_dir` from `app.core.config`.
3. Implement a safe layout: `projects/{project_id}/documents/{document_id}/raw`, `parsed`, `pages`, and `vectors`.
4. Generate server-side paths; never trust user-provided filenames for storage paths.
5. Add helpers to save raw upload files, parsed Markdown, structured JSON, and optionally page text.
6. Add helpers to read artifacts where useful.
7. Prevent path traversal by resolving paths under the configured storage root.
8. Do not expose local filesystem paths in public API schemas.
9. Add unit tests for path generation and path traversal prevention if practical.

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

- [ ] `backend/app/storage/paths.py` exists.
- [ ] `backend/app/storage/file_store.py` exists.
- [ ] Raw file, Markdown, and structured JSON can be saved in predictable locations.
- [ ] User filenames cannot escape the configured storage root.
- [ ] Storage abstraction can later be replaced by object storage.
- [ ] Existing tests pass.
```
