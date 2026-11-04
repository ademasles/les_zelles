import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from zelles.config import Settings
from zelles.llm.base import LLMError, Message
from zelles.llm.ollama import OllamaLLM
from zelles.llm.openai_compat import OpenAICompatibleLLM, extract_json
from zelles.llm.registry import create_llm, split_spec

URL = "http://llm.test/v1/chat/completions"


class Out(BaseModel):
    value: int


def _reply(content: str, prompt: int = 10, completion: int = 5) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    )


def test_split_spec_keeps_model_tags() -> None:
    assert split_spec("ollama:qwen3:8b") == ("ollama", "qwen3:8b")
    with pytest.raises(LLMError):
        split_spec("qwen3")


def test_registry() -> None:
    settings = Settings(llm_model="none")
    assert create_llm("none", settings) is None
    llm = create_llm("ollama:qwen3:8b", settings)
    assert llm is not None and llm.name == "ollama:qwen3:8b"
    with pytest.raises(LLMError):
        create_llm("acme:model", settings)


def test_extract_json_tolerates_fences() -> None:
    assert extract_json('```json\n{"value": 3}\n```') == {"value": 3}
    assert extract_json('Sure! {"value": 4} done') == {"value": 4}


@respx.mock
async def test_structured_output_with_local_pricing() -> None:
    route = respx.post(URL).mock(return_value=_reply('{"value": 7}'))
    llm = OpenAICompatibleLLM("ollama", "qwen3:8b", base_url="http://llm.test/v1")
    result = await llm.complete(system="s", messages=[Message("user", "u")], schema=Out)
    assert result.parsed == Out(value=7)
    assert result.usage.cost_usd == 0.0
    sent = route.calls[0].request.read()
    assert b'"json_schema"' in sent and b'"temperature":0' in sent


@respx.mock
async def test_repair_round_trip() -> None:
    respx.post(URL).mock(side_effect=[_reply('{"value": "seven"}'), _reply('{"value": 7}')])
    llm = OpenAICompatibleLLM("vllm", "m", base_url="http://llm.test/v1")
    result = await llm.complete(system="s", messages=[Message("user", "u")], schema=Out)
    assert result.parsed == Out(value=7)
    assert result.usage.calls == 2


@respx.mock
async def test_falls_back_to_json_mode() -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(400, text="response_format json_schema unsupported"),
            _reply('{"value": 1}'),
        ]
    )
    llm = OpenAICompatibleLLM("llamacpp", "m", base_url="http://llm.test/v1")
    result = await llm.complete(system="s", messages=[Message("user", "u")], schema=Out)
    assert result.parsed == Out(value=1)
    assert b'"json_object"' in route.calls[1].request.read()


@respx.mock
async def test_retries_then_fails() -> None:
    respx.post(URL).mock(return_value=httpx.Response(503, text="busy"))
    llm = OpenAICompatibleLLM("openai", "m", base_url="http://llm.test/v1", max_retries=1)
    with pytest.raises(LLMError, match="503"):
        await llm.complete(system="s", messages=[Message("user", "u")])


def test_local_servers_get_a_longer_timeout() -> None:
    settings = Settings(llm_model="none")
    local = create_llm("llamacpp:local", settings)
    cloud = create_llm("openai:m", settings)
    assert isinstance(local, OpenAICompatibleLLM) and local.timeout_s == 600
    assert isinstance(cloud, OpenAICompatibleLLM) and cloud.timeout_s == 180
    pinned = create_llm("ollama:m", Settings(llm_model="none", llm_timeout_s=30))
    assert isinstance(pinned, OpenAICompatibleLLM) and pinned.timeout_s == 30


@respx.mock
async def test_read_timeout_is_reported_and_not_retried() -> None:
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    llm = OpenAICompatibleLLM("ollama", "m", base_url="http://llm.test/v1", timeout_s=5)
    with pytest.raises(LLMError, match="no reply within 5 s"):
        await llm.complete(system="s", messages=[Message("user", "u")])
    assert route.call_count == 1


OLLAMA_CHAT = "http://ollama.test/api/chat"


def _ollama_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"message": {"content": content}, "prompt_eval_count": 12, "eval_count": 4},
    )


@respx.mock
async def test_ollama_uses_native_chat_without_thinking() -> None:
    route = respx.post(OLLAMA_CHAT).mock(return_value=_ollama_reply('{"value": 3}'))
    llm = create_llm(
        "ollama:granite4.2:8b",
        Settings(llm_model="none", llm_base_url="http://ollama.test/v1", ollama_num_ctx=16384),
    )
    assert isinstance(llm, OllamaLLM)
    result = await llm.complete(system="s", messages=[Message("user", "u")], schema=Out)
    assert result.parsed == Out(value=3)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 4)
    sent = json.loads(route.calls[0].request.read())
    assert sent["think"] is False and sent["stream"] is False
    assert sent["options"] == {"temperature": 0, "num_predict": 4096, "num_ctx": 16384}
    assert sent["format"]["properties"]["value"]["type"] == "integer"


@respx.mock
async def test_ollama_falls_back_to_json_format() -> None:
    route = respx.post(OLLAMA_CHAT).mock(
        side_effect=[httpx.Response(400, text="invalid format"), _ollama_reply('{"value": 1}')]
    )
    llm = OllamaLLM("m", base_url="http://ollama.test")
    result = await llm.complete(system="s", messages=[Message("user", "u")], schema=Out)
    assert result.parsed == Out(value=1)
    assert json.loads(route.calls[1].request.read())["format"] == "json"
