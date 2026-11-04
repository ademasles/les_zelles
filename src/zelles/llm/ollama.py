"""Ollama through its native `/api/chat` endpoint.

The OpenAI-compatible endpoint cannot set the context window or turn off
reasoning. Both matter on a local GPU: Ollama's default window (4096 tokens on
small cards) silently cuts the start of long prompts, and thinking models such
as granite4 or qwen3 can spend the whole token budget reasoning and return no
JSON at all.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from zelles.domain.spec import Usage
from zelles.llm.openai_compat import OpenAICompatibleLLM
from zelles.llm.pricing import cost_usd


class OllamaLLM(OpenAICompatibleLLM):
    def __init__(
        self, model: str, *, num_ctx: int = 8192, think: bool = False, **kwargs: Any
    ) -> None:
        super().__init__("ollama", model, **kwargs)
        self.base_url = self.base_url.removesuffix("/v1")
        self.context_tokens = num_ctx
        self.think = think

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/api/chat"

    def _payload(
        self, chat: list[dict[str, str]], schema: type[BaseModel] | None, max_tokens: int
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": chat,
            "stream": False,
            "think": self.think,
            "options": {
                "temperature": 0,
                "num_predict": max_tokens,
                "num_ctx": self.context_tokens,
            },
        }
        if schema is not None:
            payload["format"] = (
                schema.model_json_schema() if self._json_schema_supported else "json"
            )
        return payload

    def _reply_text(self, data: dict[str, Any]) -> str:
        return str((data.get("message") or {}).get("content") or "")

    def _account(self, usage: Usage, data: dict[str, Any]) -> None:
        prompt = int(data.get("prompt_eval_count") or 0)
        completion = int(data.get("eval_count") or 0)
        call = Usage(calls=1, input_tokens=prompt, output_tokens=completion)
        call.cost_usd = cost_usd(self.price, prompt, completion, 0)
        usage.add(call)
