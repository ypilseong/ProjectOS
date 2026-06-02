import asyncio
import json
import re

from openai import AsyncOpenAI

from app.config import config

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
_CLAUDE_USAGE_TOTALS = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "web_search_requests": 0,
    "web_fetch_requests": 0,
    "total_cost_usd": 0.0,
    "models": {},
}


def reset_llm_usage() -> None:
    _CLAUDE_USAGE_TOTALS["calls"] = 0
    _CLAUDE_USAGE_TOTALS["input_tokens"] = 0
    _CLAUDE_USAGE_TOTALS["output_tokens"] = 0
    _CLAUDE_USAGE_TOTALS["cache_creation_input_tokens"] = 0
    _CLAUDE_USAGE_TOTALS["cache_read_input_tokens"] = 0
    _CLAUDE_USAGE_TOTALS["web_search_requests"] = 0
    _CLAUDE_USAGE_TOTALS["web_fetch_requests"] = 0
    _CLAUDE_USAGE_TOTALS["total_cost_usd"] = 0.0
    _CLAUDE_USAGE_TOTALS["models"] = {}


def get_llm_usage() -> dict:
    return json.loads(json.dumps(_CLAUDE_USAGE_TOTALS))


def _record_claude_usage(data: dict) -> None:
    _CLAUDE_USAGE_TOTALS["calls"] += 1
    usage = data.get("usage") or {}
    _CLAUDE_USAGE_TOTALS["input_tokens"] += usage.get("input_tokens", 0)
    _CLAUDE_USAGE_TOTALS["output_tokens"] += usage.get("output_tokens", 0)
    _CLAUDE_USAGE_TOTALS["cache_creation_input_tokens"] += usage.get("cache_creation_input_tokens", 0)
    _CLAUDE_USAGE_TOTALS["cache_read_input_tokens"] += usage.get("cache_read_input_tokens", 0)
    server_tool_use = usage.get("server_tool_use") or {}
    _CLAUDE_USAGE_TOTALS["web_search_requests"] += server_tool_use.get("web_search_requests", 0)
    _CLAUDE_USAGE_TOTALS["web_fetch_requests"] += server_tool_use.get("web_fetch_requests", 0)
    _CLAUDE_USAGE_TOTALS["total_cost_usd"] += data.get("total_cost_usd", 0.0) or 0.0

    for model, model_usage in (data.get("modelUsage") or {}).items():
        totals = _CLAUDE_USAGE_TOTALS["models"].setdefault(
            model,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "web_search_requests": 0,
                "cost_usd": 0.0,
            },
        )
        totals["input_tokens"] += model_usage.get("inputTokens", 0)
        totals["output_tokens"] += model_usage.get("outputTokens", 0)
        totals["cache_creation_input_tokens"] += model_usage.get("cacheCreationInputTokens", 0)
        totals["cache_read_input_tokens"] += model_usage.get("cacheReadInputTokens", 0)
        totals["web_search_requests"] += model_usage.get("webSearchRequests", 0)
        totals["cost_usd"] += model_usage.get("costUSD", 0.0) or 0.0


def _messages_to_text(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"<system>\n{content}\n</system>")
        elif role == "assistant":
            parts.append(f"<assistant>\n{content}\n</assistant>")
        else:
            parts.append(content)
    return "\n\n".join(parts)


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = _JSON_FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch not in "{[":
                continue
            try:
                obj, _ = decoder.raw_decode(text[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        raise


class _OpenAIBackend:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=config.LLM_API_KEY or "not-needed",
            base_url=config.LLM_BASE_URL,
            timeout=180.0,
            max_retries=1,
        )

    def _inference_params(self) -> dict:
        extra_body: dict = {
            "top_k": config.LLM_TOP_K,
            "min_p": config.LLM_MIN_P,
            "repetition_penalty": config.LLM_REPETITION_PENALTY,
        }
        if config.LLM_THINKING_MODE:
            extra_body["chat_template_kwargs"] = {"enable_thinking": True}
        return {
            "temperature": config.LLM_TEMPERATURE,
            "top_p": config.LLM_TOP_P,
            "presence_penalty": config.LLM_PRESENCE_PENALTY,
            "extra_body": extra_body,
        }

    @staticmethod
    def _strip_think(text: str) -> str:
        return _THINK_RE.sub("", text).strip()

    async def chat(self, messages: list[dict], **kwargs) -> str:
        request_timeout = kwargs.pop("request_timeout", config.LLM_REQUEST_TIMEOUT)
        params = {**self._inference_params(), **kwargs}
        resp = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                **params,
            ),
            timeout=request_timeout,
        )
        return self._strip_think(resp.choices[0].message.content)

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        text = await self.chat(
            messages,
            response_format={"type": "json_object"},
            **kwargs,
        )
        return json.loads(text)

    async def stream(self, messages: list[dict], **kwargs):
        params = {**self._inference_params(), **kwargs}
        stream = await self._client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            stream=True,
            **params,
        )
        in_think = False
        buf = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if not delta:
                continue
            buf += delta
            while True:
                if in_think:
                    end = buf.find("</think>")
                    if end >= 0:
                        in_think = False
                        buf = buf[end + 8:]
                    else:
                        buf = ""
                        break
                else:
                    start = buf.find("<think>")
                    if start >= 0:
                        if start > 0:
                            yield buf[:start]
                        in_think = True
                        buf = buf[start + 7:]
                    else:
                        safe = max(0, len(buf) - 7)
                        if safe > 0:
                            yield buf[:safe]
                            buf = buf[safe:]
                        break
        if buf and not in_think:
            yield buf


class _ClaudeCodeBackend:
    """Calls the `claude` CLI subprocess. No separate API key needed."""

    def __init__(self, disable_plugins: bool = False):
        self.disable_plugins = disable_plugins

    def _base_cmd(self, output_format: str) -> list[str]:
        cmd = ["claude", "-p", "--output-format", output_format]
        if self.disable_plugins:
            cmd.extend(["--setting-sources", "project,local", "--disable-slash-commands"])
        return cmd

    async def _exec(self, prompt: str, output_format: str = "json") -> tuple[str, str, int]:
        cmd = self._base_cmd(output_format)
        if config.CLAUDE_CODE_MODEL:
            cmd.extend(["--model", config.CLAUDE_CODE_MODEL])
        cmd.append(prompt)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(), stderr.decode(), proc.returncode

    async def chat(self, messages: list[dict], **kwargs) -> str:
        prompt = _messages_to_text(messages)
        stdout, stderr, rc = await self._exec(prompt)
        if rc != 0:
            raise RuntimeError(f"claude CLI error (rc={rc}): {stderr.strip()}")
        data = json.loads(stdout)
        _record_claude_usage(data)
        return data.get("result", "")

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        msgs = list(messages)
        if msgs and msgs[-1].get("role") == "user":
            msgs[-1] = {
                **msgs[-1],
                "content": msgs[-1]["content"] + "\n\nRespond with valid JSON only. No markdown, no explanation.",
            }
        text = await self.chat(msgs)
        return _extract_json(text)

    async def stream(self, messages: list[dict], **kwargs):
        prompt = _messages_to_text(messages)
        cmd = ["claude", "-p", "--verbose", "--output-format", "stream-json"]
        if self.disable_plugins:
            cmd.extend(["--setting-sources", "project,local", "--disable-slash-commands"])
        if config.CLAUDE_CODE_MODEL:
            cmd.extend(["--model", config.CLAUDE_CODE_MODEL])
        cmd.append(prompt)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        yielded = False
        async for line in proc.stdout:
            line = line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                etype = event.get("type")
                if etype == "result":
                    _record_claude_usage(event)
                if etype == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                yield text
                                yielded = True
                elif etype == "result" and not yielded:
                    result = event.get("result", "")
                    if result:
                        yield result
            except json.JSONDecodeError:
                continue
        stderr = await proc.stderr.read()
        rc = await proc.wait()
        if rc != 0:
            raise RuntimeError(f"claude CLI stream error (rc={rc}): {stderr.decode().strip()}")


class LLMClient:
    def __init__(self, backend: str | None = None, disable_plugins: bool = False):
        selected = backend or config.LLM_BACKEND
        if selected in {"claude_code", "claude"}:
            self._impl: _OpenAIBackend | _ClaudeCodeBackend = _ClaudeCodeBackend(
                disable_plugins=disable_plugins
            )
        else:
            self._impl = _OpenAIBackend()

    @classmethod
    def for_role(cls, role: str, disable_plugins: bool = False) -> "LLMClient":
        from app.utils.routing import route

        return cls(backend=route(role), disable_plugins=disable_plugins)

    async def chat(self, messages: list[dict], **kwargs) -> str:
        return await self._impl.chat(messages, **kwargs)

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        return await self._impl.chat_json(messages, **kwargs)

    async def stream(self, messages: list[dict], **kwargs):
        async for token in self._impl.stream(messages, **kwargs):
            yield token
