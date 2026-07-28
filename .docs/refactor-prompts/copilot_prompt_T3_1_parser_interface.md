# GitHub Copilot Prompt - T3.1 Add Parser Interface

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


Implement ticket T3.1: Add Parser Interface.

## Objective

Introduce a document parser abstraction so Analyse-DCE does not depend directly on one implementation. Define internal parsed document objects that support Markdown and provenance metadata.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/preprocessing/`
- `backend/app/storage/`

## Tasks

1. Create `backend/app/preprocessing/parsers/` with `__init__.py`, `base.py`, and `registry.py`.
2. Create internal models for ParsedDocument, ParsedPage, ParsedBlock, and ParsedTable, either in `backend/app/preprocessing/schemas.py` or `parsers/base.py`.
3. Define a `DocumentParser` Protocol/base interface with a `parse(file_path: Path) -> ParsedDocument` method.
4. Include parser_name, parser_version, markdown, structured_data, pages, blocks, tables, metadata, and parsing_stats in ParsedDocument.
5. Add minimal placeholder classes or stubs for Docling, PyMuPDF, and Tesseract parser implementations if useful, but do not implement full parsing yet.
6. Add a parser registry that selects parser by settings/file extension where minimal and safe.
7. Add tests for parsed object construction and parser interface imports.

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

- [ ] `DocumentParser` abstraction exists.
- [ ] ParsedDocument supports Markdown and structured provenance data.
- [ ] Parser registry exists or is stubbed clearly.
- [ ] No route depends directly on Docling/PyMuPDF/Tesseract.
- [ ] Existing tests pass.
```
