# GitHub Copilot Prompt - T4.3 Add Retriever

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


Implement ticket T4.3: Add Retriever.

## Objective

Separate retrieval from answer generation. The retriever embeds a question, queries the vector store, applies filters, and returns scored candidate chunks without calling the LLM.



## Files to inspect first

- `REFACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/rag/retriever.py`
- `backend/app/rag/embeddings.py`
- `backend/app/rag/vector_store.py`

## Tasks

1. Create `backend/app/rag/retriever.py`.
2. Define a RetrievalResult data model or Pydantic/dataclass object.
3. Use the embedding service to embed user questions.
4. Use the VectorStore interface to search.
5. Support optional filters for project_id/document_id.
6. Return candidates with chunk_id, text, score, document_id, page info, section title, heading path, and metadata.
7. Do not call the LLM in retriever.
8. Add unit tests with mocked embedding service and vector store.

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

- [ ] Retriever can be tested without LLM.
- [ ] Retriever returns scored chunks with metadata.
- [ ] RAG answer generation can call retriever later.
- [ ] Existing tests pass.
```
