# GitHub Copilot Prompt - T3.4 Add Markdown-Aware Chunking

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


Implement ticket T3.4: Add Markdown-Aware Chunking.

## Objective

Replace or extend naive chunking with Markdown-aware, section-aware chunking that preserves section hierarchy and provenance metadata for RAG.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/preprocessing/chunking.py`
- `backend/app/preprocessing/markdown/`

## Tasks

1. Create `backend/app/preprocessing/markdown/` with `__init__.py`, `markdown_cleaner.py`, and `section_splitter.py`.
2. Implement heading-aware splitting for Markdown headings.
3. Build or preserve a heading path for each section.
4. Split by section first, then split oversized sections by paragraph/list/table boundaries.
5. Apply limited overlap only inside the same section.
6. Return chunk objects/dicts with document_id, chunk_index, text, markdown, heading_path, section_title, page_start, page_end, source_block_ids, token_count, and metadata.
7. Keep fallback chunking for plain text if Markdown has no headings.
8. Add tests covering headings, nested headings, bullets, tables, and long sections.

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

- [ ] Markdown chunker preserves heading path and section title.
- [ ] Long sections are split without destroying tables/lists unnecessarily.
- [ ] Chunks include required metadata fields.
- [ ] Plain text fallback exists.
- [ ] Chunking tests pass.
- [ ] Existing tests pass.
```
