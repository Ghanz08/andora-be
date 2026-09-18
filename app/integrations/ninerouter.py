from openai import AsyncOpenAI
from app.config import settings


class NineRouterClient:
    def __init__(self):
        self.base_url = settings.NINEROUTER_BASE_URL
        self.api_key = settings.NINEROUTER_API_KEY or "dummy_key"
        self.model = settings.NINEROUTER_MODEL
        self._client: AsyncOpenAI | None = None

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )
        return self._client

    async def generate_response(self, messages: list[dict]) -> str:
        """Call 9router (OpenAI-compatible) gateway with messages list"""
        client = self.get_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        choice = response.choices[0]
        return choice.message.content or ""


ninerouter_client = NineRouterClient()
