"""Hybrid retrieval over one document: BM25 plus optional dense vectors, fused with RRF.

Retrieval is always scoped to one CCTP (a few hundred chunks at most), so an
in-process index is both the fastest and the cheapest option: no vector
database to run. Vectors are persisted next to the document as a ``.npy`` file.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from zelles.domain.documents import Chunk
from zelles.llm.base import Embedder
from zelles.retrieval.bm25 import BM25

RRF_K = 60


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    lexical_rank: int | None = None
    dense_rank: int | None = None


def index_text(chunk: Chunk) -> str:
    """Text used for indexing: the section path adds the context a bare paragraph lacks."""
    return " ".join([*chunk.section_path, chunk.text])


def rrf(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


class DocumentIndex:
    def __init__(
        self,
        chunks: list[Chunk],
        vectors: npt.NDArray[np.float32] | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.chunks = chunks
        self.bm25 = BM25([index_text(c) for c in chunks])
        self.vectors = _normalize(vectors) if vectors is not None and len(vectors) else None
        self.embedder = embedder

    @classmethod
    async def build(cls, chunks: list[Chunk], embedder: Embedder | None = None) -> DocumentIndex:
        vectors = None
        if embedder is not None and chunks:
            raw = await embedder.embed([index_text(c) for c in chunks])
            vectors = np.asarray(raw, dtype=np.float32)
        return cls(chunks, vectors, embedder)

    async def search(self, query: str, k: int = 6, *, lot: str | None = None) -> list[Hit]:
        if not self.chunks:
            return []
        candidates = [i for i, c in enumerate(self.chunks) if lot is None or c.lot == lot]
        lexical = self.bm25.scores(query)
        lex_rank = [i for i in sorted(candidates, key=lambda i: -lexical[i]) if lexical[i] > 0]
        rankings = [lex_rank]
        dense_rank: list[int] = []
        if self.vectors is not None and self.embedder is not None:
            q = _normalize(np.asarray(await self.embedder.embed([query]), dtype=np.float32))[0]
            sims = self.vectors @ q
            dense_rank = sorted(candidates, key=lambda i: -float(sims[i]))[: max(k * 3, 20)]
            rankings.append(dense_rank)
        fused = rrf(rankings)
        ordered = sorted(fused, key=lambda i: -fused[i])[:k]
        lex_pos = {idx: r for r, idx in enumerate(lex_rank)}
        dense_pos = {idx: r for r, idx in enumerate(dense_rank)}
        return [Hit(self.chunks[i], fused[i], lex_pos.get(i), dense_pos.get(i)) for i in ordered]


def _normalize(matrix: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)
