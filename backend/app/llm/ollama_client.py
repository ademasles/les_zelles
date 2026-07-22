"""Ollama LLM client implementation."""

from __future__ import annotations

import logging

import requests

from app.core.config import settings
from app.llm.base import LLMClient

logger = logging.getLogger(__name__)


class OllamaClient(LLMClient):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.llm_model

    def generate(self, prompt: str, temperature: float = 0.1) -> str:
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
