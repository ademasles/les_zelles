"""Retriever — embeds questions, queries vector store, returns scored chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore


@dataclass
class RetrievalResult:
    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class Retriever:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
    ) -> None:
        self._emb = embedding_service
        self._vs = vector_store

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        query_vec = self._emb.embed_query(question)
        results = self._vs.search(query_vec, top_k=top_k, filters=filters)
        return [
            RetrievalResult(
                chunk_id=r["chunk_id"],
                text=r["metadata"].get("text", ""),
                score=r["score"],
                metadata=r["metadata"],
            )
            for r in results
        ]
