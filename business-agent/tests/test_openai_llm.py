"""Проверка клиента OpenAI через локальный сервер (без реальных вызовов)."""
import json

import pytest
from aiohttp import web

from app.ai.llm import ImageInput, LLMError, LLMNotConfigured, LLMRefusal, LLMUnavailable, OpenAILLM, build_llm
from app.ai.schemas import DIALOGUE_DECISION_SCHEMA
from app.config import Settings


@pytest.fixture
async def api():
    state = {"requests": [], "status": 200, "message": {"content": json.dumps({"ok": True})}, "finish": "stop"}

    async def completions(request: web.Request):
        state["requests"].append({"body": await request.json(), "headers": dict(request.headers)})
        if state["status"] != 200:
            return web.json_response({"error": {"message": "boom"}}, status=state["status"])
        return web.json_response({"choices": [{"message": {"role": "assistant", **state["message"]},
                                               "finish_reason": state["finish"]}]})

    app = web.Application()
    app.router.add_post("/v1/chat/completions", completions)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/v1", state
    await runner.cleanup()


async def test_request_shape(api):
    url, state = api
    state["message"] = {"content": json.dumps({k: None for k in DIALOGUE_DECISION_SCHEMA["required"]})}
    llm = OpenAILLM("key", base_url=url)
    content = [{"type": "text", "text": "hi"}, ImageInput(b"\x89PNG", "image/png").to_block()]
    try:
        out = await llm.generate_json(system="SYS", content=content, schema=DIALOGUE_DECISION_SCHEMA, effort="xhigh")
    finally:
        await llm.close()
    assert set(out) == set(DIALOGUE_DECISION_SCHEMA["required"])
    req = state["requests"][0]
    body = req["body"]
    assert req["headers"]["Authorization"] == "Bearer key"
    assert body["model"] == "gpt-5-mini"
    assert body["reasoning_effort"] == "high"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    parts = body["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "hi"}
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body["response_format"]["json_schema"]["schema"] == DIALOGUE_DECISION_SCHEMA


async def test_non_reasoning_model_has_no_effort(api):
    url, state = api
    llm = OpenAILLM("key", model="gpt-4o", base_url=url)
    try:
        await llm.generate_json(system="S", content=[{"type": "text", "text": "x"}], schema={"type": "object"})
    finally:
        await llm.close()
    assert "reasoning_effort" not in state["requests"][0]["body"]


@pytest.mark.parametrize(("status", "exc"), [(401, LLMNotConfigured), (429, LLMUnavailable), (500, LLMUnavailable),
                                             (400, LLMError)])
async def test_http_errors(api, status, exc):
    url, state = api
    state["status"] = status
    llm = OpenAILLM("key", base_url=url)
    try:
        with pytest.raises(exc):
            await llm.generate_json(system="S", content=[{"type": "text", "text": "x"}], schema={"type": "object"})
    finally:
        await llm.close()


async def test_refusal_and_truncation(api):
    url, state = api
    llm = OpenAILLM("key", base_url=url)
    try:
        state["message"] = {"content": None, "refusal": "no"}
        with pytest.raises(LLMRefusal):
            await llm.generate_json(system="S", content=[{"type": "text", "text": "x"}], schema={"type": "object"})
        state["message"] = {"content": "{\"a\""}
        state["finish"] = "length"
        with pytest.raises(LLMError):
            await llm.generate_json(system="S", content=[{"type": "text", "text": "x"}], schema={"type": "object"})
    finally:
        await llm.close()


async def test_provider_selection():
    base = {"bot_token": "1:x", "_env_file": None}
    assert build_llm(Settings(**base)) is None
    s = Settings(**base, openai_api_key="sk-x")
    assert s.llm_provider == "openai" and s.llm_model == "gpt-5-mini"
    llm = build_llm(s)
    assert isinstance(llm, OpenAILLM)
    s2 = Settings(**base, openai_api_key="sk-x", anthropic_api_key="sk-ant-x")
    assert s2.llm_provider == "anthropic" and s2.llm_model == "claude-opus-5-5"
    s3 = Settings(**base, openai_api_key="sk-x", anthropic_api_key="sk-ant-x", ai_provider="openai")
    assert s3.llm_provider == "openai"
