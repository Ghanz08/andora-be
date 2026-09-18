from types import SimpleNamespace

import pytest

from app.config import Settings
from app.integrations.ninerouter import AssistantGenerationError, NineRouterClient


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeCompletions(response))


def response_with(content, *, finish_reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def test_default_ninerouter_token_budget_leaves_room_for_reasoning_tokens():
    assert Settings().NINEROUTER_MAX_TOKENS == 2048


@pytest.mark.asyncio
async def test_generate_response_returns_text_and_uses_configured_token_budget(monkeypatch):
    monkeypatch.setattr("app.integrations.ninerouter.settings.NINEROUTER_MAX_TOKENS", 777)
    client = NineRouterClient()
    fake_client = FakeClient(response_with("Baik, saya bantu."))
    client._client = fake_client

    result = await client.generate_response([{"role": "user", "content": "Halo"}])

    assert result == "Baik, saya bantu."
    assert fake_client.chat.completions.kwargs["max_tokens"] == 777


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, "", "   "])
async def test_generate_response_rejects_empty_assistant_content(content):
    client = NineRouterClient()
    client._client = FakeClient(response_with(content))

    with pytest.raises(AssistantGenerationError) as raised:
        await client.generate_response([{"role": "user", "content": "Halo"}])

    assert raised.value.status_code == 502
    assert "empty assistant response" in raised.value.safe_detail


@pytest.mark.asyncio
async def test_generate_response_rejects_empty_choices():
    client = NineRouterClient()
    client._client = FakeClient(SimpleNamespace(choices=[], usage=None))

    with pytest.raises(AssistantGenerationError) as raised:
        await client.generate_response([{"role": "user", "content": "Halo"}])

    assert raised.value.status_code == 502
    assert "empty choices" in raised.value.safe_detail


@pytest.mark.asyncio
async def test_generate_response_reports_length_finish_without_content():
    client = NineRouterClient()
    client._client = FakeClient(response_with(None, finish_reason="length"))

    with pytest.raises(AssistantGenerationError) as raised:
        await client.generate_response([{"role": "user", "content": "Halo"}])

    assert raised.value.status_code == 502
    assert "finish_reason=length" in raised.value.safe_detail
