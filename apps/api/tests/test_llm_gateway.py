import json

import httpx
import pytest

from ocl_api.config import Settings
from ocl_api.llm.gateway import LLMError, LLMGateway, LLMTruncated, parse_json_text


def _settings(**over) -> Settings:
    base = dict(
        OLLAMA_MODEL="gemma4:26b",
        OLLAMA_KEEP_ALIVE="10m",
        OLLAMA_NUM_CTX="32768",
        OLLAMA_BASE_URL="http://ollama.test:11434",
    )
    base.update(over)
    return Settings(_env_file=None, **{k.lower(): v for k, v in base.items()})


def _gateway(handler, **over) -> LLMGateway:
    return LLMGateway(
        _settings(**over), client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_ollama_request_carries_shared_server_options() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "prompt_eval_count": 12,
                "eval_count": 5,
            },
        )

    r = _gateway(handler).chat_json("sys", "user", schema={"type": "object"})
    assert r.data == {"ok": True}
    assert seen["url"] == "http://ollama.test:11434/api/chat"
    body = seen["body"]
    assert body["model"] == "gemma4:26b"
    assert body["keep_alive"] == "10m"
    assert body["options"]["num_ctx"] == 32768
    assert body["options"]["temperature"] == 0
    assert body["think"] is False
    assert body["format"] == {"type": "object"}
    assert r.usage.prompt_tokens == 12 and r.usage.completion_tokens == 5 and r.usage.calls == 1


def test_json_fence_and_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "not json at all" if calls["n"] == 1 else '```json\n{"a": [1, 2]}\n```'
        return httpx.Response(200, json={"message": {"content": content}, "eval_count": 1})

    r = _gateway(handler).chat_json("s", "u")
    assert r.data == {"a": [1, 2]} and r.usage.calls == 2 and r.usage.retries == 1


def test_gives_up_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "nope"}})

    with pytest.raises(LLMError):
        _gateway(handler).chat_json("s", "u", retries=1)


def test_http_error_is_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(LLMError):
        _gateway(handler).chat_json("s", "u", retries=0)


def test_parse_json_text_variants() -> None:
    assert parse_json_text('{"x": 1}') == {"x": 1}
    assert parse_json_text("ผลลัพธ์:\n```json\n[1, 2]\n```") == [1, 2]
    assert parse_json_text('คำตอบคือ {"k": "ค่า"} ครับ') == {"k": "ค่า"}


def test_gemini_not_configured() -> None:
    gw = _gateway(lambda r: httpx.Response(200), LLM_PROVIDER="gemini")
    with pytest.raises(LLMError):
        gw.chat_json("s", "u")


def test_truncated_reply_raises_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"message": {"content": '{"a": [1, 2'}, "done_reason": "length", "eval_count": 9},
        )

    with pytest.raises(LLMTruncated) as ei:
        _gateway(handler).chat_json("s", "u", max_tokens=9)
    assert calls["n"] == 1 and ei.value.usage is not None and ei.value.usage.completion_tokens == 9


def test_hris_pin_is_sent_as_numeric_minus_one() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "{}"}})

    _gateway(
        handler, OLLAMA_MODEL="gemma4:12b", OLLAMA_KEEP_ALIVE="-1", OLLAMA_NUM_CTX=""
    ).chat_json("s", "u")
    assert seen["body"]["keep_alive"] == -1 and "num_ctx" not in seen["body"]["options"]
