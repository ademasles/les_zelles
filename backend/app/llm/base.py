"""LLM client interface definition."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.1) -> str: ...
