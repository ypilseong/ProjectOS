from openai import AsyncOpenAI

from app.config import config


class EmbeddingClient:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key="not-needed",
            base_url=config.EMBEDDING_BASE_URL,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in resp.data]
