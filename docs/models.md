# Models and cost

Set the model with `ZELLES_LLM_MODEL` (or `-m` on the CLI) as `provider:model`.

| Provider | Example | Notes |
|---|---|---|
| none | `none` | Rules only. Free, offline, deterministic. |
| Ollama | `ollama:qwen3:8b` | Local. `OLLAMA_HOST` is honoured. |
| llama.cpp server | `llamacpp:local` | Local, `llama-server` on port 8080. |
| vLLM, LM Studio | `vllm:<model>`, `lmstudio:<model>` | Local or self-hosted GPU. |
| Anthropic | `anthropic:claude-sonnet-5-5` | Official SDK, structured outputs, prompt caching. |
| OpenAI, Mistral, Gemini, OpenRouter | `mistral:<model>` | OpenAI-compatible presets. |
| Any OpenAI-compatible server | `openai-compatible:<model>` + `ZELLES_LLM_BASE_URL` | |

Embeddings (`ZELLES_EMBEDDING_MODEL`) use any OpenAI-compatible `/embeddings` endpoint; `ollama:bge-m3` is a good multilingual default.

## Which one to choose

- **Getting started, or confidential documents with no GPU:** `none`. The rules cover the fields estimators check first.
- **Local, private, free per document:** an 8B to 14B instruct model through Ollama with `ZELLES_LLM_CONCURRENCY=1` on a single GPU. Verification filters most of what a small model gets wrong.
- **Best quality:** `anthropic:claude-sonnet-5-5`, or `anthropic:claude-opus-5-5` for long, messy CCTPs.

Use `zelles eval -m <model>` on your own golden cases to decide; the report includes cost.

## Cost per document

The extractor makes 5 calls (one per field group) plus one for the summary. A short document (up to about 24k characters, roughly 6k tokens) goes whole into the system prompt, which is cached, so calls 2 to 5 read it at the cache rate. A longer CCTP is not sent whole: each group gets only its retrieved passages, capped at about 14k characters (roughly 4k tokens). So the cost per document stays nearly flat whatever the CCTP length, at about 30k input and 8k output tokens in total.

Order of magnitude with Anthropic pricing (USD per million tokens, October 2026):

| Model | Input / output / cache read | Estimate per document |
|---|---|---|
| claude-haiku-5-5 | 0.10 / 0.50 / n.a. | about $0.01 |
| claude-sonnet-5-5 | 2 / 10 / 0.20 | about $0.15 |
| claude-opus-5-5 | 4 / 20 / 0.20 | about $0.30 |
| any local model | 0 | electricity only |

These are estimates; every analysis records the real token counts and cost in the spec sheet (`usage`). Prices change: override them with `ZELLES_LLM_PRICE_INPUT_PER_MTOK` and `ZELLES_LLM_PRICE_OUTPUT_PER_MTOK`.

## How a provider is called

- **OpenAI-compatible adapter:** sends a JSON schema in `response_format`; falls back to `json_object` if the server rejects it (older llama.cpp or Ollama builds), then validates with Pydantic and asks once for a repair if needed. Retries with exponential backoff on 429 and 5xx.
- **Anthropic adapter:** uses `messages.parse` with the Pydantic schema, marks the system prompt (instructions plus the document) with `cache_control`, enables server-side model fallbacks for the models that support them, and treats a `refusal` stop reason as an error instead of parsing it.
