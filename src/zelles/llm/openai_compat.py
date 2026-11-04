"""Adapter for any server that speaks the OpenAI Chat Completions API.

Covers local runtimes (Ollama, llama.cpp server, vLLM, LM Studio) and cloud
APIs (OpenAI, Mistral, Gemini's OpenAI endpoint, OpenRouter). Structured output
uses JSON-schema constrained decoding when the server supports it, falls back
to JSON mode, and always validates with Pydantic, with one repair round-trip.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from zelles.domain.spec import Usage
from zelles.llm.base import Completion, LLMError, Message, T
from zelles.llm.pricing import Price, cost_usd, price_for

log = logging.getLogger(__name__)

PRESETS: dict[str, tuple[str, str | None]] = {
    # provider: (default base URL, environment variable holding the API key)
    "ollama": ("http://localhost:11434/v1", None),
    "llamacpp": ("http://localhost:8080/v1", None),
    "vllm": ("http://localhost:8000/v1", None),
    "lmstudio": ("http://localhost:1234/v1", None),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "openai-compatible": ("http://localhost:8000/v1", None),
}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def default_base_url(provider: str) -> str:
    if provider == "ollama" and (host := os.environ.get("OLLAMA_HOST")):
        host = host if host.startswith("http") else f"http://{host}"
        return host.rstrip("/") + "/v1"
    return PRESETS.get(provider, PRESETS["openai-compatible"])[0]


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and leading prose."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0), default=-1)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


class OpenAICompatibleLLM:
    def __init__(
        self,
        provider: str,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 180.0,
        max_retries: int = 2,
        max_output_tokens: int = 4096,
        price: Price | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider, self.model = provider, model
        self.name = f"{provider}:{model}"
        self.base_url = (base_url or default_base_url(provider)).rstrip("/")
        env_key = PRESETS.get(provider, (None, None))[1]
        key = api_key or (os.environ.get(env_key) if env_key else None)
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = client or httpx.AsyncClient(timeout=timeout_s, headers=headers)
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.price = price_for(provider, model, override=price)
        self._json_schema_supported = True

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(url, json=payload)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise LLMError(f"{self.name}: cannot reach {url}: {exc}") from exc
            else:
                if response.status_code < 400:
                    data: dict[str, Any] = response.json()
                    return data
                retryable = response.status_code in (408, 409, 429) or response.status_code >= 500
                if not retryable or attempt == self.max_retries:
                    raise LLMError(
                        f"{self.name}: HTTP {response.status_code}: {response.text[:500]}"
                    )
            await asyncio.sleep(delay)
            delay *= 2
        raise LLMError(f"{self.name}: retries exhausted")  # pragma: no cover

    async def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T] | None = None,
        max_tokens: int | None = None,
    ) -> Completion[T]:
        chat: list[dict[str, str]] = [{"role": "system", "content": system}]
        chat += [{"role": m.role, "content": m.content} for m in messages]
        usage = Usage()
        started = time.perf_counter()

        for repair_round in range(2):
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": chat,
                "max_tokens": max_tokens or self.max_output_tokens,
                "temperature": 0,
            }
            if schema is not None:
                payload["response_format"] = self._response_format(schema)
            try:
                data = await self._post(payload)
            except LLMError as exc:
                if schema is not None and self._json_schema_supported and "HTTP 400" in str(exc):
                    log.info("%s rejected json_schema; falling back to JSON mode", self.name)
                    self._json_schema_supported = False
                    payload["response_format"] = self._response_format(schema)
                    data = await self._post(payload)
                else:
                    raise
            self._account(usage, data)
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            if schema is None:
                usage.seconds = time.perf_counter() - started
                return Completion(text=text, parsed=None, usage=usage, model=self.name)
            try:
                parsed = schema.model_validate(extract_json(text))
            except (ValueError, ValidationError) as exc:
                if repair_round == 1:
                    raise LLMError(f"{self.name}: invalid structured output: {exc}") from exc
                chat += [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": "Your reply was not valid JSON for the schema. Error:\n"
                        f"{str(exc)[:1500]}\nReply again with only the corrected JSON.",
                    },
                ]
                continue
            usage.seconds = time.perf_counter() - started
            return Completion(text=text, parsed=parsed, usage=usage, model=self.name)
        raise LLMError(f"{self.name}: no valid output")  # pragma: no cover

    def _response_format(self, schema: type[BaseModel]) -> dict[str, Any]:
        if self._json_schema_supported:
            return {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
            }
        return {"type": "json_object"}

    def _account(self, usage: Usage, data: dict[str, Any]) -> None:
        raw = data.get("usage") or {}
        prompt = int(raw.get("prompt_tokens") or 0)
        completion = int(raw.get("completion_tokens") or 0)
        cached = int((raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        call = Usage(
            calls=1, input_tokens=prompt, output_tokens=completion, cached_input_tokens=cached
        )
        call.cost_usd = cost_usd(self.price, prompt, completion, cached)
        usage.add(call)


class OpenAICompatibleEmbedder:
    """Embeddings through `/v1/embeddings` (Ollama `bge-m3`, OpenAI, vLLM...)."""

    def __init__(
        self,
        provider: str,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        batch_size: int = 32,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = f"{provider}:{model}"
        self.model = model
        self.base_url = (base_url or default_base_url(provider)).rstrip("/")
        env_key = PRESETS.get(provider, (None, None))[1]
        key = api_key or (os.environ.get(env_key) if env_key else None)
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = client or httpx.AsyncClient(timeout=timeout_s, headers=headers)
        self.batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = await self._client.post(
                f"{self.base_url}/embeddings", json={"model": self.model, "input": batch}
            )
            if response.status_code >= 400:
                raise LLMError(f"{self.name}: HTTP {response.status_code}: {response.text[:300]}")
            items = sorted(response.json()["data"], key=lambda d: d["index"])
            vectors.extend(item["embedding"] for item in items)
        return vectors

    async def aclose(self) -> None:
        await self._client.aclose()
