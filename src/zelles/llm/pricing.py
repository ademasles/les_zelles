"""Price table used for cost estimates (USD per million tokens).

Local providers cost nothing per token. Cloud prices change: override them
with ZELLES_LLM_PRICE_INPUT_PER_MTOK / ZELLES_LLM_PRICE_OUTPUT_PER_MTOK.
"""

from __future__ import annotations

from dataclasses import dataclass

LOCAL_PROVIDERS = frozenset({"ollama", "llamacpp", "vllm", "lmstudio", "fake"})


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cached_input: float | None = None


# Anthropic first-party rates, as published in October 2026.
KNOWN_PRICES: dict[str, Price] = {
    "anthropic:claude-opus-5-5": Price(4.0, 20.0, 0.20),
    "anthropic:claude-sonnet-5-5": Price(2.0, 10.0, 0.20),
    "anthropic:claude-haiku-5-5": Price(0.10, 0.50),
}


def price_for(provider: str, model: str, *, override: Price | None = None) -> Price | None:
    if override is not None:
        return override
    if provider in LOCAL_PROVIDERS:
        return Price(0.0, 0.0, 0.0)
    return KNOWN_PRICES.get(f"{provider}:{model}")


def cost_usd(
    price: Price | None, input_tokens: int, output_tokens: int, cached: int = 0
) -> float | None:
    if price is None:
        return None
    cached_rate = price.cached_input if price.cached_input is not None else price.input
    fresh = max(input_tokens - cached, 0)
    return (fresh * price.input + cached * cached_rate + output_tokens * price.output) / 1_000_000
