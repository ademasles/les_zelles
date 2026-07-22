# ADR-001: Vector Store Strategy

**Status:** Accepted  
**Date:** 2026-07-22  
**Deciders:** Architecture team  
**Tags:** storage, vectors, search, POC, pilot  

---

## Context

Analyse-DCE requires vector search for retrieving semantically relevant document chunks during RAG-based question answering.

The application needs a vector store that:

- Supports embedding-based similarity search (L2 distance)
- Can be rebuilt from persisted chunks
- Works locally for POC without external services
- Supports metadata filtering (by document_id, project_id)
- Can scale to production workloads

## Decision

**FAISS (Facebook AI Similarity Search)** behind a `VectorStore` abstract interface for the POC phase.

The `VectorStore` interface is defined in `backend/app/rag/vector_store.py` and provides:

- `add_chunks(chunk_ids, embeddings, metadata)` — index chunks
- `search(query_embedding, top_k, filters)` — retrieve nearest neighbors
- `delete_document(document_id)` — remove document from index
- `save(path)` / `load(path)` — persist/restore index

`FaissVectorStore` implements this interface using `faiss.IndexFlatL2`.

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| **PostgreSQL + pgvector** | Preferred for pilot; not suitable for POC without PostgreSQL setup |
| **Qdrant** | Production option if scale/filtering/latency requires dedicated vector DB |
| **Chroma** | Adds a new dependency without clear benefit over FAISS for the POC |
| **Pinecone / Weaviate** | External services; POC must work fully offline |

## Consequences

### Positive

- FAISS is lightweight, local, and has no external dependencies
- The `VectorStore` interface isolates the rest of the code from implementation details
- Migration to pgvector or Qdrant requires only a new class implementing `VectorStore`
- FAISS indexes can be persisted and rebuilt from SQL chunks

### Risks

- FAISS is in-memory; large document collections may exceed available RAM
- FAISS does not natively support metadata filtering — current implementation filters post-search
- FAISS is not distributed; indexes cannot be shared across processes
- No built-in support for hybrid (vector + keyword) search without additional tooling

## Migration Path

### Pilot (Pgvector)

1. Implement `PgVectorStore(VectorStore)` in `app/rag/pgvector_store.py`
2. Add `pgvector` extension to PostgreSQL
3. Replace `FaissVectorStore` instantiation in `ProcessingService` with `PgVectorStore`
4. Vector search uses SQL-level filtering, eliminating post-filtering

### Production (Qdrant)

1. Implement `QdrantVectorStore(VectorStore)` in `app/rag/qdrant_store.py`
2. Run Qdrant as a sidecar or managed service
3. Update configuration to `vector_store=qdrant`
4. Benefit from native filtering, horizontal scaling, and lower latency at scale

---

## Related Documents

- `REFACTOR_DECISIONS.md` §8 Vector Store Strategy
- `backend/app/rag/vector_store.py` — Interface and FAISS implementation
- `backend/app/core/config.py` — `vector_store` configuration setting
