# GitHub Copilot Prompt - T2.1 Define Minimal POC Database Models

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


Implement ticket T2.1: Define Minimal POC Database Models.

## Objective

Create the minimal SQLAlchemy model layer required for a traceable RAG POC: projects, documents, processing jobs, pages, chunks, questions, answers, citations, and feedback. Keep the schema SQLite-compatible while preparing for a future PostgreSQL migration.



## Files to inspect first

- `REFRACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/database/`
- `backend/database/database.py`

## Tasks

1. Inspect existing database/session/model code and preserve current behaviour where possible.
2. Create or update `backend/app/database/base.py` and `backend/app/database/session.py` if needed.
3. Create SQLAlchemy models under `backend/app/models/` for Project, Document, ProcessingJob, Page, Chunk, Question, Answer, AnswerCitation, and Feedback.
4. Use string IDs or UUID-compatible string fields to remain SQLite-friendly.
5. Represent JSON-like fields such as heading paths, source block IDs, and metadata in a SQLite-compatible way, for example JSON/Text depending on current SQLAlchemy version.
6. Ensure Document stores filename, content type, status, parser name/version, storage artifact references, and error message.
7. Ensure Chunk stores text, markdown, page_start, page_end, section_title, heading_path, source_block_ids, token_count, and metadata.
8. Ensure AnswerCitation links an answer to a chunk and stores quote, page range, section title, and score.
9. Do not introduce Alembic yet unless already present.
10. Add lightweight model import tests if safe.

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

- [ ] `backend/app/models/` contains the required model files.
- [ ] Models import successfully.
- [ ] Schema supports answer traceability from answer to citation to chunk to document.
- [ ] Schema remains SQLite-compatible.
- [ ] Existing tests pass.
- [ ] No broad route/service/RAG refactor is performed.
```
