"""Provider-agnostic LLM interface.

The rest of the code depends only on :class:`LLM` and :class:`Embedder`.
Adapters exist for every OpenAI-compatible server (Ollama, llama.cpp, vLLM,
LM Studio, OpenAI, Mistral, Gemini, OpenRouter...) and for Anthropic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

from zelles.domain.spec import Usage

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when a provider call fails after retries or returns unusable output."""


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class Completion[T: BaseModel]:
    text: str
    parsed: T | None
    usage: Usage = field(default_factory=Usage)
    model: str = ""


class LLM(Protocol):
    """A chat model that can return validated structured output."""

    name: str

    async def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T] | None = None,
        max_tokens: int | None = None,
    ) -> Completion[T]: ...

    async def aclose(self) -> None: ...


class Embedder(Protocol):
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def aclose(self) -> None: ...
