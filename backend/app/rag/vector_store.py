"""VectorStore interface and FAISS implementation."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    def add_chunks(
        self,
        chunk_ids: list[str],
        embeddings: np.ndarray,
        metadata: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def delete_document(self, document_id: str) -> None: ...

    def save(self, path: Path) -> None: ...

    def load(self, path: Path) -> None: ...


class FaissVectorStore:
    def __init__(self) -> None:
        self._index: Any = None
        self._chunk_ids: list[str] = []
        self._metadata: list[dict[str, Any]] = []

    def add_chunks(
        self,
        chunk_ids: list[str],
        embeddings: np.ndarray,
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        import faiss

        if self._index is None:
            dim = embeddings.shape[1]
            self._index = faiss.IndexFlatL2(dim)

        self._index.add(embeddings)
        self._chunk_ids.extend(chunk_ids)
        if metadata:
            self._metadata.extend(metadata)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self._index is None or self._index.ntotal == 0:
            return []

        distances, indices = self._index.search(query_embedding.reshape(1, -1), top_k)

        results = []
        for dist, idx in zip(distances[0], indices[0], strict=False):
            if idx < 0 or idx >= len(self._chunk_ids):
                continue
            results.append({
                "chunk_id": self._chunk_ids[idx],
                "score": float(1.0 / (1.0 + dist)),
                "metadata": self._metadata[idx] if idx < len(self._metadata) else {},
            })

        return results

    def delete_document(self, document_id: str) -> None:
        keep_ids: list[str] = []
        keep_meta: list[dict[str, Any]] = []
        for cid, meta in zip(self._chunk_ids, self._metadata, strict=False):
            if meta.get("document_id") != document_id:
                keep_ids.append(cid)
                keep_meta.append(meta)

        removed = len(self._chunk_ids) - len(keep_ids)
        if removed:
            self._chunk_ids = keep_ids
            self._metadata = keep_meta
            self._rebuild_index()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "index": self._index,
                "chunk_ids": self._chunk_ids,
                "metadata": self._metadata,
            }, f)

    def load(self, path: Path) -> None:
        if path.exists():
            with open(path, "rb") as f:
                data = pickle.load(f)
            self._index = data["index"]
            self._chunk_ids = data["chunk_ids"]
            self._metadata = data["metadata"]

    def _rebuild_index(self) -> None:
        import faiss

        if not self._chunk_ids:
            self._index = None
            return
        dim = self._index.d
        self._index = faiss.IndexFlatL2(dim)
        if self._chunk_ids:
            self._index.add(np.zeros((len(self._chunk_ids), dim), dtype=np.float32))
