# GitHub Copilot Prompt - T3.3 Add Parser Fallback Policy

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


Implement ticket T3.3: Add Parser Fallback Policy.

## Objective

Add deterministic parser fallback orchestration: Docling first, PyMuPDF fallback for simple born-digital PDFs, Tesseract fallback for scanned/low-text documents, and clean failure reporting.



## Files to inspect first

- `REFRACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/preprocessing/parsers/`
- `backend/app/services/`

## Tasks

1. Implement or update parser registry/factory to choose candidates based on file extension and settings.
2. Create minimal PyMuPDF and Tesseract parser implementations or clear stubs if not already present.
3. Define fallback order: Docling -> PyMuPDF where appropriate -> Tesseract where appropriate.
4. Log parser attempts and failures without logging full document content.
5. Return parsing_stats indicating fallback used, parser attempts, duration, and warnings.
6. Ensure failures are explicit and catchable by future ProcessingService.
7. Add tests with mocked parser implementations to verify fallback order and failure behaviour.

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

- [ ] Fallback order is deterministic.
- [ ] Parser attempt/failure metadata is captured.
- [ ] All parser failures produce a clear error.
- [ ] No exceptions are silently swallowed.
- [ ] Tests verify fallback ordering with mocks.
- [ ] Existing tests pass.
```
