from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.voice_agent import conversation_id_from_room, handle_final_transcript


def test_conversation_id_from_room():
    assert conversation_id_from_room("andora-abc-123") == "abc-123"


@pytest.mark.parametrize("room_name", ["other-abc", "andora-", ""])
def test_conversation_id_from_room_rejects_invalid_names(room_name: str):
    with pytest.raises(ValueError):
        conversation_id_from_room(room_name)


@pytest.mark.asyncio
async def test_empty_final_transcript_is_ignored():
    session = MagicMock()

    with patch(
        "app.voice_agent.andora_agent.process_turn",
        new_callable=AsyncMock,
    ) as process_turn:
        await handle_final_transcript(
            session=session,
            conversation_id="conversation-1",
            user_id="user-1",
            transcript="   ",
        )

    process_turn.assert_not_awaited()
    session.say.assert_not_called()


@pytest.mark.asyncio
async def test_final_transcript_is_persisted_and_spoken():
    session = MagicMock()
    assistant_message = {
        "role": "assistant",
        "content": "Baik, saya bantu sekarang.",
    }

    with patch(
        "app.voice_agent.andora_agent.process_turn",
        new_callable=AsyncMock,
        return_value=({"role": "user"}, assistant_message),
    ) as process_turn:
        await handle_final_transcript(
            session=session,
            conversation_id="conversation-1",
            user_id="user-1",
            transcript="  Tolong bantu saya  ",
        )

    process_turn.assert_awaited_once_with(
        conversation_id="conversation-1",
        user_id="user-1",
        user_text="Tolong bantu saya",
        modality="voice",
    )
    session.say.assert_called_once_with(
        "Baik, saya bantu sekarang.",
        allow_interruptions=True,
        add_to_chat_ctx=False,
    )
