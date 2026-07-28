# GitHub Copilot Prompt - T4.2 Add VectorStore Interface With FAISS Implementation

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


Implement ticket T4.2: Add VectorStore Interface With FAISS Implementation.

## Objective

Isolate FAISS behind a VectorStore interface so future migration to pgvector or Qdrant does not require rewriting RAG service logic.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/rag/`
- `backend/app/storage/`

## Tasks

1. Create `backend/app/rag/vector_store.py` defining a VectorStore Protocol/base class.
2. Create `backend/app/rag/faiss_store.py` implementing the interface with FAISS.
3. Support add_chunks, search, delete_document, save, and load where practical.
4. Ensure search results include chunk_id, score, and metadata.
5. Keep FAISS imports only in `faiss_store.py` if possible.
6. Persist local FAISS index under the storage layout where practical.
7. Do not introduce pgvector/Qdrant in this ticket.
8. Add tests using small fake vectors or a mocked FAISS store.

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

- [ ] `VectorStore` interface exists.
- [ ] `FaissVectorStore` implementation exists.
- [ ] RAG code can depend on the interface, not FAISS directly.
- [ ] Search returns chunk IDs and scores.
- [ ] Existing tests pass.
```
