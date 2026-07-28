# FAISS Persistence Design

## Current-State Findings

Based on an audit of `backend/app/rag/vector_store.py` and `backend/app/main.py`:
1. **Ownership**: A single global `FaissVectorStore` instance is attached to `app.state.retriever` at application startup.
2. **Filtering limitation**: It uses `faiss.IndexFlatL2` which does not support pre-filtering by metadata. Currently, searches evaluate all vectors globally, which means queries could leak or over-fetch across projects.
3. **Index mapping**: Integer FAISS positions map to string chunk IDs via a Python list (`self._chunk_ids`).
4. **Deletion bug**: Document deletion incorrectly rebuilds the index using zero-filled arrays instead of real embeddings, effectively destroying the vectors.
5. **Lack of durability**: State is kept in memory. Save/load methods exist but lack atomic writes, locking, and are not integrated into the mutation lifecycle or the application lifespan.
6. **No embeddings in SQL**: Because the SQLite `chunks` table stores text but not embeddings, losing the FAISS index means we must re-run the embedding model to rebuild.

## Chosen Ownership Model

**Project-Specific Indexes Managed Globally**

A single global FAISS index is **not appropriate** because plain FAISS (`IndexFlatL2`) cannot enforce relational metadata filtering (e.g., restricting a search to a specific `project_id`) without risking over-fetching and discarding valid results.

Instead, the global `VectorStore` instance will manage a dictionary of project-specific FAISS indexes (`Dict[project_id, ProjectIndex]`).
- When a search is requested for Project A, only Project A's index is queried.
- This strictly enforces project boundary isolation.
- Document-specific filtering within a project is small enough that we can use candidate over-fetching followed by metadata filtering, but project boundaries must be physically isolated.

## Persistence Artifact Format

We will persist one file per project to limit contention and blast radius:
`data/vector_store/{project_id}.pkl`

The pickled dictionary will contain:
```python
{
    "version": "1.0",
    "embedding_model": "sentence-transformers/...",
    "dimension": 384,
    "index": faiss.IndexFlatL2,
    "chunk_ids": list[str],
    "metadata": list[dict[str, Any]],
    "embeddings": np.ndarray  # Preserved to allow correct document deletion
}
```

*Note: Storing the raw numpy `embeddings` array allows us to safely rebuild the `IndexFlatL2` when a document is deleted, without requiring `IndexIDMap`.*

## Metadata Schema

The `metadata` dictionary for each vector must minimally include:
- `document_id`: To support targeted deletions.
- `chunk_index`: To maintain ordering.
- `text`: For retrieval context (if not loaded directly from SQL during retrieval).

The artifact wrapper must include `embedding_model` and `dimension` to detect compatibility mismatches upon load.

## Mutation/Checkpoint Lifecycle

1. **Addition**: `ProcessingService` completes embedding a document -> adds chunks to the project's index -> `VectorStore` immediately checkpoints the project's `.pkl` file to disk.
2. **Deletion**: Chunks matching `document_id` are removed from `chunk_ids`, `metadata`, and `embeddings` -> a new `IndexFlatL2` is populated -> the project's `.pkl` is checkpointed.
3. **Atomic Writes**: All checkpoints will be written to a temporary file (e.g., `{project_id}.pkl.tmp`) and then atomically renamed via `os.replace` (or `Path.replace`) to prevent corruption if the process crashes mid-write.

## Startup and Shutdown Lifecycle

- **Startup**: The FastAPI `lifespan` hook initializes `FaissVectorStore`, which scans `data/vector_store/` and loads all valid `.pkl` files into memory.
- **Shutdown**: As a defence in depth, the `lifespan` hook will call a `save_all()` method on shutdown to ensure any pending state is flushed, though explicit checkpointing on mutation makes this a secondary fallback.

## Corruption and Compatibility Behaviour

- If a `.pkl` file is corrupted (fails to unpickle) or its `embedding_model` does not match the current `settings.embedding_model`, the artifact will be **rejected and deleted/renamed to .bak**.
- The project will behave as if it has a missing (empty) index.
- A warning will be emitted to the application logs.

## Concurrency Model

- **In-Process**: Because FastAPI routes and background tasks run concurrently in the same process, we will use a per-project `asyncio.Lock` to serialize reads (`search`) and writes (`add_chunks`, `delete_document`) for a given project.
- **Multi-Process limitations**: This file-based, in-memory POC relies on in-process locks. It **must operate as a single backend worker** (`workers=1` in Uvicorn/Docker). The design will document this limitation.

## Rebuild Strategy

Since embeddings are not stored in the SQLite database, a lost or incompatible index requires hitting the embedding model again.
- We will provide an administrative script or internal endpoint (`POST /api/projects/{project_id}/rebuild-index`).
- The rebuild process will:
  1. Fetch all `Chunk` rows for the project from SQL.
  2. Re-run `EmbeddingService.embed_chunks(...)` on the text.
  3. Re-insert the embeddings into the vector store.
  4. Checkpoint to disk.

## Test Plan

- **Concurrency tests**: Verify that overlapping searches and chunk additions for the same project do not corrupt the index, using `asyncio.gather`.
- **Atomic write tests**: Mock `os.replace` to simulate a crash and ensure the original index file remains intact.
- **Deletion tests**: Verify that deleting a document correctly removes its vectors and that searches no longer return its chunks.
- **Compatibility tests**: Attempt to load a `.pkl` saved with a different `embedding_model` and ensure it is safely rejected.

## Files Expected to Change

- `backend/app/rag/vector_store.py`: Implement project-level indexes, atomic saves, locking, and deletion logic.
- `backend/app/main.py`: Update lifespan for startup loading and shutdown saving.
- `backend/app/core/config.py`: Add `vector_store_dir` setting.
- `backend/tests/unit/test_vector_store.py`: New unit tests for persistence, concurrency, and deletion.
- `.env.example`: Add `VECTOR_STORE_DIR`.

## Rejected Alternatives

1. **Global Index with Metadata Post-Filtering**: FAISS `IndexFlatL2` evaluates distance before we can filter. If we query a global index, the top K results might belong entirely to Project B, leaving Project A with 0 results after filtering.
2. **FAISS `IndexIDMap`**: While it supports explicit IDs, it does not solve the project isolation/filtering problem natively. Project-specific indexes are cleaner.
3. **Storing Embeddings in SQLite**: Would avoid re-computing embeddings on rebuild, but blobs bloat SQLite quickly and slow down retrieval. It is better to defer this to a PostgreSQL + pgvector migration in the pilot phase.
