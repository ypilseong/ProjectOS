import asyncio
import json
import re

from openai import AsyncOpenAI

from app.config import config

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMClient:
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
