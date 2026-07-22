"""Compat — delegates to new embeddings/retrieval."""

from __future__ import annotations

from app.rag.embeddings import EmbeddingService

embedding_model = EmbeddingService()


def filter_chunks(summaries: list[dict], query: str, top_k: int = 5) -> list[dict]:
    import numpy as np

    query_vec = embedding_model.embed_query(query)
    texts = [s.get("summary", s.get("text", "")) for s in summaries]
    if not texts:
        return []

    vecs = embedding_model.embed_chunks(texts)
    scores = np.dot(vecs, query_vec) / (
        np.linalg.norm(vecs, axis=1) * np.linalg.norm(query_vec) + 1e-10
    )

    top_indices = np.argsort(scores)[-top_k:][::-1]
    return [{**summaries[i], "score": float(scores[i])} for i in top_indices]
