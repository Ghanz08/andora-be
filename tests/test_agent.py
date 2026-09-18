from unittest.mock import AsyncMock, patch

import pytest

from app.agent.agent import AndoraAgent
from app.integrations.ninerouter import AssistantGenerationError


@pytest.mark.asyncio
async def test_agent_rechecks_owner_before_writes():
    agent = AndoraAgent()

    with patch(
        "app.agent.agent.SupabaseService.get_conversation_async",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_conversation, patch(
        "app.agent.agent.SupabaseService.add_message_async",
        new_callable=AsyncMock,
    ) as add_message:
        with pytest.raises(PermissionError):
            await agent.process_turn(
                conversation_id="conversation-1",
                user_id="user-1",
                user_text="Tolong bantu saya",
                modality="voice",
            )

    get_conversation.assert_awaited_once_with("conversation-1", "user-1")
    add_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_does_not_save_assistant_when_generation_fails():
    agent = AndoraAgent()
    user_message = {"id": "user-msg", "role": "user", "content": "Tolong", "modality": "text"}

    with patch(
        "app.agent.agent.SupabaseService.get_conversation_async",
        new_callable=AsyncMock,
        return_value={"id": "conversation-1", "user_id": "user-1"},
    ), patch(
        "app.agent.agent.SupabaseService.add_message_async",
        new_callable=AsyncMock,
        return_value=user_message,
    ) as add_message, patch(
        "app.agent.agent.SupabaseService.list_messages_async",
        new_callable=AsyncMock,
        return_value=[user_message],
    ), patch(
        "app.agent.agent.ninerouter_client.generate_response",
        new_callable=AsyncMock,
        side_effect=AssistantGenerationError("empty assistant response", status_code=502),
    ):
        with pytest.raises(AssistantGenerationError):
            await agent.process_turn(
                conversation_id="conversation-1",
                user_id="user-1",
                user_text="Tolong",
                modality="text",
            )

    assert add_message.await_count == 1
    assert add_message.await_args.kwargs["role"] == "user"
