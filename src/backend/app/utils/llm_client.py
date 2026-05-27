import json
from openai import AsyncOpenAI
from app.config import config


class LLMClient:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=config.LLM_API_KEY or "not-needed",
            base_url=config.LLM_BASE_URL,
            timeout=180.0,
            max_retries=1,
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        resp = await self._client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            **kwargs,
        )
        return resp.choices[0].message.content

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        text = await self.chat(
            messages,
            response_format={"type": "json_object"},
            **kwargs,
        )
        return json.loads(text)

    async def stream(self, messages: list[dict], **kwargs):
        stream = await self._client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
