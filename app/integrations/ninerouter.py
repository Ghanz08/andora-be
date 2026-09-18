from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from app.config import settings


class AssistantGenerationError(RuntimeError):
    def __init__(self, safe_detail: str, *, status_code: int = 502):
        super().__init__(safe_detail)
        self.safe_detail = safe_detail
        self.status_code = status_code


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
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=settings.NINEROUTER_MAX_TOKENS,
            )
        except APIConnectionError as error:
            raise AssistantGenerationError("Assistant service unavailable", status_code=503) from error
        except APIStatusError as error:
            status_code = 503 if error.status_code >= 500 else 502
            raise AssistantGenerationError("Assistant service unavailable", status_code=status_code) from error

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise AssistantGenerationError("Assistant service returned empty choices")

        choice: Any = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            detail = "Assistant service returned empty assistant response"
            if finish_reason:
                detail = f"{detail} (finish_reason={finish_reason})"
            raise AssistantGenerationError(detail)

        return content.strip()


ninerouter_client = NineRouterClient()
