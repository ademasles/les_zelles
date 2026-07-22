"""Embedding service — centralized model loading and embedding generation."""

from __future__ import annotations

import logging

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model: %s", self.model_name)

    def embed_query(self, text: str) -> np.ndarray:
        self._load_model()
        return self._model.encode(text, convert_to_numpy=True)

    def embed_chunks(self, texts: list[str]) -> np.ndarray:
        self._load_model()
        return self._model.encode(texts, convert_to_numpy=True)
