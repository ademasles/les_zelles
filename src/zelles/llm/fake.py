"""Deterministic LLM for tests and offline demos."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from zelles.domain.spec import Usage
from zelles.llm.base import Completion, Message, T

Responder = Callable[[str, list[Message], type[Any] | None], Any]


class FakeLLM:
    """Returns whatever ``responder(system, messages, schema)`` produces.

    The responder may return a dict (validated against the schema), a model
    instance, or a string.
    """

    def __init__(self, responder: Responder, name: str = "fake:model") -> None:
        self.responder = responder
        self.name = name
        self.calls: list[tuple[str, list[Message]]] = []

    async def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T] | None = None,
        max_tokens: int | None = None,
    ) -> Completion[T]:
        self.calls.append((system, messages))
        out = self.responder(system, messages, schema)
        usage = Usage(
            calls=1, input_tokens=sum(len(m.content) // 4 for m in messages), cost_usd=0.0
        )
        if schema is None:
            return Completion(text=str(out), parsed=None, usage=usage, model=self.name)
        parsed = out if isinstance(out, schema) else schema.model_validate(out)
        return Completion(
            text=parsed.model_dump_json(), parsed=parsed, usage=usage, model=self.name
        )

    async def aclose(self) -> None:
        return None


class HashEmbedder:
    """Bag-of-trigrams hashing embedder: no model, deterministic, good enough for tests."""

    name = "hash:trigram"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import zlib  # noqa: PLC0415

        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            folded = f"  {text.lower()}  "
            for i in range(len(folded) - 2):
                vec[zlib.crc32(folded[i : i + 3].encode()) % self.dim] += 1.0
            out.append(vec)
        return out

    async def aclose(self) -> None:
        return None
