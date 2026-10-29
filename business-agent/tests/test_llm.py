"""Проверка формы запроса к Anthropic API через локальный сервер (без реальных вызовов)."""
import json

import anthropic
import pytest
from aiohttp import web

from app.ai.llm import AnthropicLLM, LLMError, LLMRefusal
from app.ai.schemas import DIALOGUE_DECISION_SCHEMA


@pytest.fixture
async def api():
    state = {"requests": [], "reply": {"ok": True}, "stop_reason": "end_turn"}

    async def messages(request: web.Request):
        body = await request.json()
        state["requests"].append({"body": body, "headers": dict(request.headers)})
        return web.json_response({
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": json.dumps(state["reply"])}],
            "stop_reason": state["stop_reason"], "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

    app = web.Application()
    app.router.add_post("/v1/messages", messages)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", state
    await runner.cleanup()


def client(url):
    return anthropic.AsyncAnthropic(api_key="test", base_url=url, max_retries=0)


async def test_request_shape(api):
    url, state = api
    llm = AnthropicLLM("test", client=client(url))
    out = await llm.generate_json(system="SYS", content=[{"type": "text", "text": "hi"}], schema=DIALOGUE_DECISION_SCHEMA,
                                  effort="low")
    assert out == {"ok": True}
    req = state["requests"][0]
    body = req["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["headers"].get("anthropic-beta", "")
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in body and "temperature" not in body


async def test_refusal_is_raised(api):
    url, state = api
    state["stop_reason"] = "refusal"
    with pytest.raises(LLMRefusal):
        await AnthropicLLM("test", client=client(url)).generate_json(system="s", content=[], schema={"type": "object"})


async def test_truncated_output_is_error(api):
    url, state = api
    state["stop_reason"] = "max_tokens"
    with pytest.raises(LLMError):
        await AnthropicLLM("test", client=client(url)).generate_json(system="s", content=[], schema={"type": "object"})


async def test_fallbacks_can_be_disabled(api):
    url, state = api
    await AnthropicLLM("test", client=client(url), server_fallbacks=False).generate_json(system="s", content=[], schema={})
    assert "fallbacks" not in state["requests"][0]["body"]
