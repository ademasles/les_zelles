# GitHub Copilot Prompt - T3.2 Implement Docling Parser

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


Implement ticket T3.2: Implement Docling Parser.

## Objective

Implement the Docling parser as the preferred parser for PDF/DOCX documents. The parser should return Markdown for RAG and structured output for provenance without deciding where artifacts are stored.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/preprocessing/parsers/base.py`
- `backend/app/preprocessing/parsers/docling_parser.py`
- `backend/pyproject.toml`

## Tasks

1. Verify `docling` is present in backend runtime dependencies.
2. Implement `backend/app/preprocessing/parsers/docling_parser.py`.
3. Use Docling to parse PDF/DOCX and export Markdown.
4. Return a ParsedDocument containing markdown, structured_data, parser_name, parser_version, pages/blocks/tables where available, metadata, and parsing_stats.
5. Handle missing Docling metadata gracefully; do not assume bounding boxes/page metadata always exist.
6. Do not save files directly inside the parser; leave persistence to storage/processing services.
7. Raise clear parser errors that a processing service can catch later.
8. Add tests using small fixtures or mocks. Do not require heavy real parsing in CI if fixtures are unavailable.

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

- [ ] `DoclingParser` exists and implements `DocumentParser`.
- [ ] Docling parser returns Markdown.
- [ ] Docling parser returns structured_data.
- [ ] Parser handles missing optional metadata gracefully.
- [ ] No FastAPI route imports Docling directly.
- [ ] Existing tests pass.
```
