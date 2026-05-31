import json

import pytest

from app.utils.llm_client import (
    _ClaudeCodeBackend,
    _OpenAIBackend,
    _extract_json,
    get_llm_usage,
    LLMClient,
    reset_llm_usage,
)


def test_extract_json_accepts_markdown_fence():
    assert _extract_json('```json\n{"ok": true}\n```') == {"ok": True}


def test_extract_json_finds_object_with_surrounding_text():
    text = 'Here is the result:\n{"ok": true, "value": 7}\nDone.'
    assert _extract_json(text) == {"ok": True, "value": 7}


def test_llm_client_backend_override_uses_local_when_global_is_claude(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "LLM_BACKEND", "claude_code")

    client = LLMClient(backend="local")

    assert isinstance(client._impl, _OpenAIBackend)


@pytest.mark.asyncio
async def test_claude_chat_records_usage(monkeypatch):
    reset_llm_usage()

    class FakeProc:
        async def communicate(self):
            return (
                json.dumps({
                    "type": "result",
                    "result": "ok",
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 3,
                        "output_tokens": 2,
                        "cache_creation_input_tokens": 11,
                        "cache_read_input_tokens": 13,
                        "server_tool_use": {
                            "web_search_requests": 0,
                            "web_fetch_requests": 0,
                        },
                    },
                    "modelUsage": {
                        "claude-sonnet": {
                            "inputTokens": 3,
                            "outputTokens": 2,
                            "cacheCreationInputTokens": 11,
                            "cacheReadInputTokens": 13,
                            "webSearchRequests": 0,
                            "costUSD": 0.01,
                        }
                    },
                }).encode(),
                b"",
            )

        @property
        def returncode(self):
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(
        "app.utils.llm_client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    backend = _ClaudeCodeBackend()
    assert await backend.chat([{"role": "user", "content": "hi"}]) == "ok"

    usage = get_llm_usage()
    assert usage["calls"] == 1
    assert usage["input_tokens"] == 3
    assert usage["output_tokens"] == 2
    assert usage["total_cost_usd"] == 0.01


@pytest.mark.asyncio
async def test_claude_stream_uses_verbose_stream_json(monkeypatch):
    calls = []

    class FakeStdout:
        def __aiter__(self):
            self._lines = iter([
                json.dumps({
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "hello"}]},
                }).encode(),
            ])
            return self

        async def __anext__(self):
            try:
                return next(self._lines)
            except StopIteration:
                raise StopAsyncIteration

    class FakeStderr:
        async def read(self):
            return b""

    class FakeProc:
        stdout = FakeStdout()
        stderr = FakeStderr()

        async def wait(self):
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc()

    monkeypatch.setattr(
        "app.utils.llm_client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    backend = _ClaudeCodeBackend()
    tokens = [token async for token in backend.stream([{"role": "user", "content": "hi"}])]

    assert tokens == ["hello"]
    assert calls[0][:5] == ("claude", "-p", "--verbose", "--output-format", "stream-json")


@pytest.mark.asyncio
async def test_claude_chat_passes_configured_model(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "CLAUDE_CODE_MODEL", "claude-haiku-4-5")
    calls = []

    class FakeProc:
        async def communicate(self):
            return (
                json.dumps({
                    "type": "result",
                    "result": "ok",
                    "usage": {},
                    "modelUsage": {"claude-haiku-4-5": {}},
                }).encode(),
                b"",
            )

        @property
        def returncode(self):
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc()

    monkeypatch.setattr(
        "app.utils.llm_client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    backend = _ClaudeCodeBackend()
    assert await backend.chat([{"role": "user", "content": "hi"}]) == "ok"

    assert "--model" in calls[0]
    assert "claude-haiku-4-5" in calls[0]
