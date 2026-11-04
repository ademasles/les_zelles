"""Anthropic adapter using the official SDK (optional extra: ``les-zelles[anthropic]``).

Uses structured outputs (``output_format`` with a Pydantic model), prompt caching
on the system prompt (shared across every field group of an analysis), and the
server-side refusal fallback on the models that support it.
"""

from __future__ import annotations

import time
from typing import Any

from zelles.domain.spec import Usage
from zelles.llm.base import Completion, LLMError, Message, T
from zelles.llm.pricing import Price, cost_usd, price_for

FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLM:
    def __init__(
        self,
        model: str = "claude-opus-5-5",
        *,
        api_key: str | None = None,
        timeout_s: float = 180.0,
        max_retries: int = 2,
        max_output_tokens: int = 4096,
        price: Price | None = None,
    ) -> None:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on extras
            raise LLMError("install the extra: pip install 'les-zelles[anthropic]'") from exc
        self._anthropic = anthropic
        self.model = model
        self.name = f"anthropic:{model}"
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )
        self.max_output_tokens = max_output_tokens
        self.price = price_for("anthropic", model, override=price)

    async def aclose(self) -> None:
        await self._client.close()

    async def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T] | None = None,
        max_tokens: int | None = None,
    ) -> Completion[T]:
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_output_tokens,
            # The system prompt is identical for every call of an analysis: cache it.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if self.model in FALLBACK_MODELS:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        try:
            if schema is not None:
                response = await self._client.beta.messages.parse(output_format=schema, **kwargs)
            elif "betas" in kwargs:
                response = await self._client.beta.messages.create(**kwargs)
            else:
                response = await self._client.messages.create(**kwargs)
        except self._anthropic.APIStatusError as exc:
            raise LLMError(f"{self.name}: HTTP {exc.status_code}: {exc.message}") from exc
        except self._anthropic.APIConnectionError as exc:
            raise LLMError(f"{self.name}: connection failed: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError(f"{self.name}: the model declined the request")
        text = "".join(getattr(b, "text", "") for b in response.content if b.type == "text")
        raw = response.usage
        cached = int(getattr(raw, "cache_read_input_tokens", 0) or 0)
        written = int(getattr(raw, "cache_creation_input_tokens", 0) or 0)
        input_tokens = int(raw.input_tokens) + cached + written
        usage = Usage(
            calls=1,
            input_tokens=input_tokens,
            output_tokens=int(raw.output_tokens),
            cached_input_tokens=cached,
            seconds=time.perf_counter() - started,
        )
        usage.cost_usd = cost_usd(self.price, input_tokens, usage.output_tokens, cached)
        parsed = getattr(response, "parsed_output", None) if schema is not None else None
        if schema is not None and parsed is None:
            raise LLMError(
                f"{self.name}: no structured output (stop_reason={response.stop_reason})"
            )
        return Completion(text=text, parsed=parsed, usage=usage, model=self.name)
