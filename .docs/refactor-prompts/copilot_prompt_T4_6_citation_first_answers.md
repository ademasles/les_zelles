# GitHub Copilot Prompt - T4.6 Implement Citation-First Answer Generation

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


Implement ticket T4.6: Implement Citation-First Answer Generation.

## Objective

Refactor QA generation so every answer is traceable to retrieved evidence and returns citations, model name, prompt version, evidence quality, and warnings.



## Files to inspect first

- `REFRACTOR_DECISIONS.md`
- `backend/app/main.py`
- `backend/app/api/routes/*.py`
- `backend/app/schemas/*.py`
- `backend/app/core/config.py`
- `backend/pyproject.toml`
- `backend/tests/`
- `backend/app/services/rag_service.py`
- `backend/app/rag/`
- `backend/app/llm/`
- `backend/app/repositories/`
- `backend/app/schemas/answer.py`

## Tasks

1. Create or update `backend/app/services/rag_service.py`.
2. Implement flow: create question -> retrieve chunks -> build prompt -> call LLM -> create citations -> persist answer and citations -> return AnswerResponse.
3. If no evidence is found, return an answer stating that the information was not found and evidence_quality=`none`.
4. Citations should include document_id, document_name, chunk_id, page_start/page_end, section_title, quote, and score.
5. Persist prompt_version, model_name, latency, evidence_quality, retrieved chunk IDs, and citations where repositories exist.
6. Do not hallucinate citations not tied to retrieved chunks.
7. Add tests with mocked retriever and mocked LLM.

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

- [ ] Answers include citations or explicit no-evidence response.
- [ ] AnswerResponse schema is used.
- [ ] Retrieved chunk IDs are traceable.
- [ ] LLM is mocked in tests.
- [ ] Existing tests pass.
```
