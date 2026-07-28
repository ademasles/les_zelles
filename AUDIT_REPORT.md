# Analyse-DCE Refactor Audit Report

## 1. Entrypoints

**Actual backend entrypoints used by environments:**
- **Local development:** Uses `backend/app/main.py` (via `backend/Makefile` running `uvicorn app.main:app`).
- **Docker:** Uses `backend/app/main.py` (via `backend/Dockerfile` running `CMD ["uvicorn", "app.main:app", ...]`).
- **Docker Compose:** Uses `backend/app/main.py` (builds from `backend/Dockerfile`).
- **Tests:** The smoke test `test_import_app.py` directly tests the `app.main` module.
- **Documentation/Guides:** Reference `uvicorn app.main:app` (found via grep in `.docs`).

**Conclusion on legacy entrypoint:**
The legacy entrypoint `backend/main.py` is no longer used by any standard workflow and can be safely removed.

---

## 2. Legacy endpoints

Implementations and consumers found for the target endpoints:

- **/save**:
  - **Implementation:** Exists in `backend/app/main.py` and `backend/main.py`. Calls `compat_save_project`.
  - **Consumers:** Frontend `api_client.py` uses `api.save_project()`, which calls `/save/`.
  - **Recommendation:** **Replace** with the existing canonical endpoint. A new `/api/projects/` router already exists in `app/api/routes/projects.py`. The frontend should be updated to use it.

- **/feedback**:
  - **Implementation:** Exists as `/api/feedback/` via `feedback_router` in `backend/app/main.py`. The legacy `/feedback/` (no prefix) still exists in `backend/main.py`.
  - **Consumers:** Frontend `app.py` uses `api.submit_feedback()`, which hits `/feedback/` without the `/api` prefix.
  - **Recommendation:** **Replace** with the existing canonical endpoint. Update the frontend `api_client.py` to point to `/api/feedback/`.

- **/train**:
  - **Implementation:** Defined directly in `backend/app/main.py` and `backend/main.py`. Spawns a subprocess to run `train_cross_encoder.py`.
  - **Consumers:** No frontend consumers (no buttons or API client calls found).
  - **Recommendation:** **Retain temporarily as a deprecated alias** (or move to an admin router) if it's still needed for offline evaluation scripts, but it shouldn't pollute `main.py`.

- **/ping**:
  - **Implementation:** Defined directly in `backend/app/main.py` and `backend/main.py`.
  - **Consumers:** None found. The frontend `api_client.py`'s `health()` function calls `/api/health`.
  - **Recommendation:** **Delete**. It is entirely superseded by the existing `/api/health` endpoint.

---

## 3. Compatibility layer

Analysis of `backend/compat.py`:

- `compat_save_project`: **Still required** (temporarily) because `/save/` is still used by the frontend. The retained behavior should eventually be migrated to `ProjectService` or the new `ProjectRepository` in the `app/api/routes/projects.py` router.
- `compat_store_feedback`: **Dead code**. It is only imported/used in the legacy `backend/main.py`. The new `/api/feedback/` endpoint uses `FeedbackRepository`. Should be **removed**.
- `compat_upload`, `compat_query`: These functions were mentioned in the `compat.py` module docstring, but they are no longer present in the file. They have **already been replaced**.

---

## 4. Database execution model

The database execution model is currently **inconsistently mixed**.

- **Synchronous SQLAlchemy:**
  - Setup: `database/database.py` creates a synchronous `engine` (with `sqlite:///`) and `SessionLocal`.
  - Usage: Legacy routes and compatibility functions still heavily use this. For example, `app/api/routes/projects.py` manually creates `db = SessionLocal()` and runs synchronous `.query()`, `.add()`, and `.commit()`. `compat_save_project` also uses it.
- **Asynchronous SQLAlchemy:**
  - Setup: `app/database/session.py` creates an `AsyncEngine` (with `sqlite+aiosqlite:///`), an `async_session_factory`, and an async `get_db()` FastAPI dependency.
  - Usage: New repositories (e.g., `ProjectRepository`, `DocumentRepository`) expect an `AsyncSession` and new routes (`uploads.py`, `project_queries.py`) use the `get_db` async generator.

---

## 5. Project and Document model

- **Semantics:**
  - `project_id`: Identifies a semantic grouping of documents (a tender).
  - `document_id`: Identifies a specific uploaded file (PDF/DOCX).
  - `doc_id`: A legacy identifier primarily used by the frontend.
- **Conflation of Identifiers:**
  - Identifiers are heavily conflated. In the frontend, users enter a project ID via `doc_id` (e.g., "AO-demo").
  - In `backend/app/api/routes/uploads.py`, `doc_id` is passed from the form and directly mapped to `project_id = doc_id`. The upload creates a `Document` with a generated UUID for `document_id`.
  - However, the frontend then calls `/queries/` using the same `doc_id` ("AO-demo"). In `backend/app/api/routes/project_queries.py`, the `run_queries` route expects `doc_id` but treats it as a `document_id` (calling `await doc_repo.get(doc_id)`). This fails because "AO-demo" is the project ID, not the generated document UUID.
- **Current Creation Flow:**
  - **Project creation:** Implicitly created (or updated) during file upload via `ProjectRepository.create_or_update()`.
  - **Upload & Document creation:** Upload creates a new `Document` row linked to the project ID, with a generated UUID.
  - **Question creation:** `run_predefined_queries` or manual Q&A creates `Question` and `Answer` rows.
  - **Retrieval scoping:** Retrieval is technically scoped to the document or global depending on the filter.
- **Schema Support:**
  - The schema **already supports** multiple documents per project. `Project` has a 1-to-N relationship with `Document` (`documents = relationship(...)`).

---

## 6. Vector-store lifecycle

- **Instantiation:** `FaissVectorStore` is instantiated once in `backend/app/main.py` inside the FastAPI `lifespan` context manager.
- **Injection:** It is passed to `Retriever`, which is attached to `app.state.retriever`. Routes get it via the `get_retriever` dependency.
- **Instances:** Only a single global instance is created and shared.
- **Scope:** The store is **global**. It holds chunks for all documents in a single FAISS index. Document separation relies on filtering after search (or parallel metadata arrays).
- **ID Mapping:** FAISS internal positions map to `chunk_id`s and metadata via parallel Python lists (`_chunk_ids` and `_metadata`).
- **Persistence:** Persistence methods (`save()`, `load()`) exist, but they are **not actively called**. The `lifespan` block has TODOs indicating that loading and teardown/saving are not yet wired up.
- **Checkpointing:** Add/delete operations are performed in memory (e.g., `delete_document` rebuilds the index from the remaining in-memory Python lists). Changes are lost on restart.
- **Concurrent Access:** It is **not safe** for concurrent writes. The `_rebuild_index` and `add_chunks` methods modify internal state (and FAISS index) without threading/async locks.
- **Embedding Compatibility:** The FAISS index infers dimension from the first batch of vectors (`dim = embeddings.shape[1]`). It assumes all subsequent embeddings use the identical dimension and model, with no internal checks for versioning.

---

## 7. Baseline validation

Results from running baseline checks in the `backend/` directory:

- **`ruff check .`**: Failed with 51 errors. Almost all errors were `F401` (unused imports, heavily in `main.py` and `app/main.py`) and one `E501` (line too long in a test).
- **`ruff format --check .`**: Failed. 10 files would be reformatted.
- **`mypy app`**: Failed with 14 errors across 5 files (e.g., invalid base class for legacy SQLAlchemy models, missing `encode` attribute on `None` in embeddings, missing requests types, and incorrect keyword arguments for `FeedbackRepository.create`).
- **`pytest`**: Failed during collection (`1 error during collection`). Missing `numpy` module dependency when trying to import `app.rag.embeddings` in `tests/evaluation/test_rag_regression.py`.
