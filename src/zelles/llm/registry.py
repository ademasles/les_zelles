"""Build LLM and embedding clients from 'provider:model' strings."""

from __future__ import annotations

from zelles.config import Settings
from zelles.llm.base import LLM, Embedder, LLMError
from zelles.llm.openai_compat import (
    LOCAL_PROVIDERS,
    PRESETS,
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
)
from zelles.llm.pricing import Price

NONE_VALUES = frozenset({"", "none", "rules", "off"})
LOCAL_TIMEOUT_S = 600.0
CLOUD_TIMEOUT_S = 180.0


def split_spec(spec: str) -> tuple[str, str]:
    """'ollama:qwen3:8b' -> ('ollama', 'qwen3:8b')."""
    provider, sep, model = spec.partition(":")
    if not sep or not model:
        raise LLMError(f"model must look like 'provider:model', got {spec!r}")
    return provider.lower(), model


def create_llm(spec: str, settings: Settings) -> LLM | None:
    """Return an LLM client, or None for rules-only mode."""
    if spec.strip().lower() in NONE_VALUES:
        return None
    provider, model = split_spec(spec)
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    timeout_s = settings.llm_timeout_s or (
        LOCAL_TIMEOUT_S if provider in LOCAL_PROVIDERS else CLOUD_TIMEOUT_S
    )
    price = None
    if (
        settings.llm_price_input_per_mtok is not None
        and settings.llm_price_output_per_mtok is not None
    ):
        price = Price(settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok)
    if provider == "anthropic":
        from zelles.llm.anthropic_llm import AnthropicLLM  # noqa: PLC0415

        return AnthropicLLM(
            model,
            api_key=api_key,
            timeout_s=timeout_s,
            max_retries=settings.llm_max_retries,
            max_output_tokens=settings.llm_max_output_tokens,
            price=price,
        )
    if provider == "ollama":
        from zelles.llm.ollama import OllamaLLM  # noqa: PLC0415

        return OllamaLLM(
            model,
            num_ctx=settings.ollama_num_ctx,
            think=settings.ollama_think,
            base_url=settings.llm_base_url,
            timeout_s=timeout_s,
            max_retries=settings.llm_max_retries,
            max_output_tokens=settings.llm_max_output_tokens,
            price=price,
        )
    if provider not in PRESETS:
        known = ", ".join(sorted([*PRESETS, "anthropic"]))
        raise LLMError(f"unknown provider {provider!r}; use one of: {known}")
    return OpenAICompatibleLLM(
        provider,
        model,
        base_url=settings.llm_base_url,
        api_key=api_key,
        timeout_s=timeout_s,
        max_retries=settings.llm_max_retries,
        max_output_tokens=settings.llm_max_output_tokens,
        price=price,
    )


def create_embedder(spec: str, settings: Settings) -> Embedder | None:
    if spec.strip().lower() in NONE_VALUES:
        return None
    provider, model = split_spec(spec)
    if provider == "hash":
        from zelles.llm.fake import HashEmbedder  # noqa: PLC0415

        return HashEmbedder()
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    return OpenAICompatibleEmbedder(
        provider, model, base_url=settings.embedding_base_url, api_key=api_key
    )
