import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.voice_agent import (
    PersistenceAgent,
    RPC_MIC_HOLD,
    RPC_MIC_RELEASE,
    TURN_COMPLETED_TOPIC,
    TURN_READY_TOPIC,
    PushToTalkController,
    conversation_id_from_room,
    create_realtime_model,
    handle_completed_turn,
    handle_console_transcript,
    handle_final_transcript,
    play_startup_greeting,
    publish_turn_completed,
    publish_turn_ready,
    resolve_voice_context,
    wire_realtime_persistence,
)
from app.integrations.ninerouter import AssistantGenerationError
from app.voice_session_agent import VOICE_TOOLS


def test_conversation_id_from_room():
    assert conversation_id_from_room("andora-abc-123") == "abc-123"


def test_realtime_model_uses_gemini_live(monkeypatch):
    monkeypatch.setattr("app.voice_models.settings.GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setattr("app.voice_models.settings.GEMINI_REALTIME_MODEL", "gemini-3.8-live")
    monkeypatch.setattr("app.voice_models.settings.GEMINI_REALTIME_VOICE", "Puck")
    monkeypatch.setattr("app.voice_models.settings.GEMINI_REALTIME_TEMPERATURE", 0.7)

    realtime_model = create_realtime_model()

    assert realtime_model.model == "gemini-3.8-live"


@pytest.mark.parametrize("room_name", ["other-abc", "andora-", ""])
def test_conversation_id_from_room_rejects_invalid_names(room_name: str):
    with pytest.raises(ValueError):
        conversation_id_from_room(room_name)


def test_console_context_does_not_require_persistent_conversation():
    assert resolve_voice_context(
        room_name="console-room",
        user_id="console-user",
        is_fake_job=True,
    ) == (None, "console-user")


def test_cloud_context_requires_andora_room():
    with pytest.raises(ValueError):
        resolve_voice_context(
            room_name="console-room",
            user_id="user-1",
            is_fake_job=False,
        )


def test_rpc_method_names():
    assert RPC_MIC_HOLD == "andora.mic.hold"
    assert RPC_MIC_RELEASE == "andora.mic.release"


def test_voice_agent_registers_document_tools(monkeypatch):
    monkeypatch.setattr("app.voice_session_agent.create_realtime_model", MagicMock(return_value=MagicMock()))
    agent = PersistenceAgent(
        conversation_id="conversation-1",
        user_id="user-1",
        console_history=[],
        realtime=True,
    )

    assert [tool.__name__ for tool in VOICE_TOOLS] == [
        "search_knowledge",
        "read_uploaded_document",
        "siapkan_pengisian_dokumen",
        "eksekusi_cetak_dokumen",
        "kirim_dokumen",
    ]
    assert [tool.__name__ for tool in agent._tools] == [tool.__name__ for tool in VOICE_TOOLS]


@pytest.mark.asyncio
async def test_empty_final_transcript_is_ignored():
    session = MagicMock()
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()

    with patch(
        "app.voice_turns.andora_agent.process_turn",
        new_callable=AsyncMock,
    ) as process_turn:
        await handle_final_transcript(
            session=session,
            conversation_id="conversation-1",
            user_id="user-1",
            transcript="   ",
            local_participant=local_participant,
            destination_identity="user-1",
        )

    process_turn.assert_not_awaited()
    payload = json.loads(local_participant.publish_data.await_args.args[0])
    assert payload == {
        "type": "andora.turn.ready",
        "conversation_id": "conversation-1",
        "reason": "empty_transcript",
    }


@pytest.mark.asyncio
async def test_realtime_conversation_items_are_persisted_and_published():
    handlers = {}
    session = MagicMock()

    def register(event_name):
        def decorator(fn):
            handlers[event_name] = fn
            return fn
        return decorator

    session.on.side_effect = register
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()
    user_message = {"id": "user-msg", "role": "user", "content": "Apa syarat beasiswa?"}
    assistant_message = {"id": "assistant-msg", "role": "assistant", "content": "Syaratnya adalah..."}

    with (
        patch(
            "app.voice_realtime.SupabaseService.get_conversation_async",
            new_callable=AsyncMock,
            return_value={"id": "conversation-1"},
        ),
        patch(
            "app.voice_realtime.SupabaseService.add_message_async",
            new_callable=AsyncMock,
            side_effect=[user_message, assistant_message],
        ) as add_message,
    ):
        wire_realtime_persistence(
            session,
            conversation_id="conversation-1",
            user_id="user-1",
            local_participant=local_participant,
            destination_identity="user-1",
        )
        user_item = SimpleNamespace(role="user", text_content="Apa syarat beasiswa?", interrupted=False)
        assistant_item = SimpleNamespace(role="assistant", text_content="Syaratnya adalah...", interrupted=False)
        handlers["conversation_item_added"](MagicMock(item=user_item))
        await asyncio.sleep(0.01)
        handlers["conversation_item_added"](MagicMock(item=assistant_item))
        await asyncio.sleep(0.01)

    assert add_message.await_args_list[0].kwargs == {
        "conversation_id": "conversation-1",
        "role": "user",
        "content": "Apa syarat beasiswa?",
        "modality": "voice",
    }
    assert add_message.await_args_list[1].kwargs == {
        "conversation_id": "conversation-1",
        "role": "assistant",
        "content": "Syaratnya adalah...",
        "modality": "voice",
    }
    completed_payload = json.loads(local_participant.publish_data.await_args_list[0].args[0])
    ready_payload = json.loads(local_participant.publish_data.await_args_list[1].args[0])
    assert completed_payload == {
        "type": "andora.turn.completed",
        "conversation_id": "conversation-1",
        "user_message": user_message,
        "assistant_message": assistant_message,
    }
    assert ready_payload == {"type": "andora.turn.ready", "conversation_id": "conversation-1"}


@pytest.mark.asyncio
async def test_startup_greeting_surfaces_tts_error_after_playout():
    session = MagicMock()
    speech = MagicMock()
    speech.wait_for_playout = AsyncMock()
    speech.exception.return_value = TimeoutError("tts timeout")
    session.say.return_value = speech

    with pytest.raises(TimeoutError, match="tts timeout"):
        await play_startup_greeting(session)

    session.say.assert_called_once_with(
        "Halo, saya Andora. Apa yang bisa saya bantu?",
        allow_interruptions=False,
        add_to_chat_ctx=False,
    )
    speech.wait_for_playout.assert_awaited_once()


@pytest.mark.asyncio
async def test_completed_turn_routes_once_to_console_handler():
    session = MagicMock()
    history: list[dict[str, str]] = []

    with patch(
        "app.voice_turns.handle_console_transcript",
        new_callable=AsyncMock,
    ) as console_handler:
        await handle_completed_turn(
            session=session,
            transcript="Tolong bantu saya",
            conversation_id=None,
            user_id="console-user",
            console_history=history,
        )

    console_handler.assert_awaited_once_with(
        session=session,
        transcript="Tolong bantu saya",
        history=history,
    )


@pytest.mark.asyncio
async def test_console_transcript_uses_in_memory_history():
    session = MagicMock()
    session.say.return_value.wait_for_playout = AsyncMock()
    session.say.return_value.exception.return_value = None
    history: list[dict[str, str]] = []

    with patch(
        "app.voice_turns.ninerouter_client.generate_response",
        new_callable=AsyncMock,
        return_value="Baik, saya bantu.",
    ) as generate_response:
        await handle_console_transcript(
            session=session,
            transcript="  Tolong bantu saya  ",
            history=history,
        )

    messages = generate_response.await_args.args[0]
    assert messages[-1] == {"role": "user", "content": "Tolong bantu saya"}
    assert history == [
        {"role": "user", "content": "Tolong bantu saya"},
        {"role": "assistant", "content": "Baik, saya bantu."},
    ]
    session.say.assert_called_once_with(
        "Baik, saya bantu.",
        allow_interruptions=False,
        add_to_chat_ctx=False,
    )
    session.say.return_value.wait_for_playout.assert_awaited_once()


@pytest.mark.asyncio
async def test_console_transcript_generation_failure_removes_pending_user_history():
    session = MagicMock()
    history: list[dict[str, str]] = []

    with patch(
        "app.voice_turns.ninerouter_client.generate_response",
        new_callable=AsyncMock,
        side_effect=AssistantGenerationError("empty assistant response", status_code=502),
    ):
        with pytest.raises(AssistantGenerationError):
            await handle_console_transcript(
                session=session,
                transcript="Tolong bantu saya",
                history=history,
            )

    assert history == []
    session.say.assert_not_called()


@pytest.mark.asyncio
async def test_session_closing_does_not_retry_fallback_speech():
    agent = PersistenceAgent(
        conversation_id=None,
        user_id="console-user",
        console_history=[],
    )
    session = MagicMock()
    agent._activity = MagicMock(session=session)
    message = MagicMock(text_content="Tolong bantu saya")

    with patch(
        "app.voice_session_agent.handle_completed_turn",
        new_callable=AsyncMock,
        side_effect=RuntimeError("AgentSession is closing, cannot use say()"),
    ):
        with pytest.raises(Exception) as raised:
            await agent.on_user_turn_completed(MagicMock(), message)

    assert raised.value.__class__.__name__ == "StopResponse"
    session.say.assert_not_called()


@pytest.mark.asyncio
async def test_realtime_cloud_agent_lets_gemini_generate_reply(monkeypatch):
    monkeypatch.setattr("app.voice_session_agent.create_realtime_model", MagicMock(return_value=MagicMock()))
    agent = PersistenceAgent(
        conversation_id="conversation-1",
        user_id="user-1",
        console_history=[],
        realtime=True,
    )
    agent._activity = MagicMock(session=MagicMock())

    with patch("app.voice_session_agent.handle_completed_turn", new_callable=AsyncMock) as handler:
        await agent.on_user_turn_completed(MagicMock(), MagicMock(text_content="Tolong"))

    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_transcript_is_persisted_and_spoken():
    session = MagicMock()
    session.say.return_value.wait_for_playout = AsyncMock()
    session.say.return_value.exception.return_value = None
    assistant_message = {
        "id": "assistant-1",
        "role": "assistant",
        "content": "Baik, saya bantu sekarang.",
        "modality": "voice",
        "created_at": "2026-09-18T00:00:01+00:00",
    }
    user_message = {
        "id": "user-1",
        "role": "user",
        "content": "Tolong bantu saya",
        "modality": "voice",
        "created_at": "2026-09-18T00:00:00+00:00",
    }
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()

    with patch(
        "app.voice_turns.andora_agent.process_turn",
        new_callable=AsyncMock,
        return_value=(user_message, assistant_message),
    ) as process_turn:
        await handle_final_transcript(
            session=session,
            conversation_id="conversation-1",
            user_id="user-1",
            transcript="  Tolong bantu saya  ",
            local_participant=local_participant,
            destination_identity="user-1",
        )

    process_turn.assert_awaited_once_with(
        conversation_id="conversation-1",
        user_id="user-1",
        user_text="Tolong bantu saya",
        modality="voice",
    )
    session.say.assert_called_once_with(
        "Baik, saya bantu sekarang.",
        allow_interruptions=False,
        add_to_chat_ctx=False,
    )
    session.say.return_value.wait_for_playout.assert_awaited_once()
    assert local_participant.publish_data.await_count == 2
    completed_call, ready_call = local_participant.publish_data.await_args_list
    payload = json.loads(completed_call.args[0])
    assert payload == {
        "type": "andora.turn.completed",
        "conversation_id": "conversation-1",
        "user_message": user_message,
        "assistant_message": assistant_message,
    }
    assert completed_call.kwargs == {
        "reliable": True,
        "destination_identities": ["user-1"],
        "topic": TURN_COMPLETED_TOPIC,
    }
    assert json.loads(ready_call.args[0]) == {
        "type": "andora.turn.ready",
        "conversation_id": "conversation-1",
    }
    assert ready_call.kwargs == {
        "reliable": True,
        "destination_identities": ["user-1"],
        "topic": TURN_READY_TOPIC,
    }


@pytest.mark.asyncio
async def test_final_transcript_generation_failure_publishes_failure_without_speech():
    session = MagicMock()
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()

    with patch(
        "app.voice_turns.andora_agent.process_turn",
        new_callable=AsyncMock,
        side_effect=AssistantGenerationError("empty assistant response", status_code=502),
    ):
        with pytest.raises(AssistantGenerationError):
            await handle_final_transcript(
                session=session,
                conversation_id="conversation-1",
                user_id="user-1",
                transcript="Tolong bantu saya",
                local_participant=local_participant,
                destination_identity="user-1",
            )

    session.say.assert_not_called()
    payload = json.loads(local_participant.publish_data.await_args.args[0])
    assert payload == {"type": "andora.turn.failed", "conversation_id": "conversation-1"}


@pytest.mark.asyncio
async def test_publish_turn_completed_falls_back_when_payload_too_large():
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()
    user_message = {"id": "user-1", "content": "x" * 70_000}
    assistant_message = {"id": "assistant-1", "content": "Baik."}

    await publish_turn_completed(
        local_participant=local_participant,
        destination_identity="user-1",
        conversation_id="conversation-1",
        user_message=user_message,
        assistant_message=assistant_message,
    )

    payload = json.loads(local_participant.publish_data.await_args.args[0])
    assert payload == {
        "type": "andora.turn.completed.fetch_required",
        "conversation_id": "conversation-1",
        "user_message_id": "user-1",
        "assistant_message_id": "assistant-1",
        "messages_url": "/conversations/conversation-1",
    }


@pytest.mark.asyncio
async def test_publish_turn_completed_falls_back_for_multibyte_payload_over_14kb():
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()
    user_message = {"id": "user-1", "content": "é" * 7_100}
    assistant_message = {"id": "assistant-1", "content": "Baik."}

    await publish_turn_completed(
        local_participant=local_participant,
        destination_identity="user-1",
        conversation_id="conversation-1",
        user_message=user_message,
        assistant_message=assistant_message,
    )

    encoded = local_participant.publish_data.await_args.args[0]
    assert len(encoded.encode("utf-8")) < 14_000
    payload = json.loads(encoded)
    assert payload == {
        "type": "andora.turn.completed.fetch_required",
        "conversation_id": "conversation-1",
        "user_message_id": "user-1",
        "assistant_message_id": "assistant-1",
        "messages_url": "/conversations/conversation-1",
    }


@pytest.mark.asyncio
async def test_publish_turn_ready_targets_owner():
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()

    await publish_turn_ready(
        local_participant=local_participant,
        destination_identity="user-1",
        conversation_id="conversation-1",
    )

    assert json.loads(local_participant.publish_data.await_args.args[0]) == {
        "type": "andora.turn.ready",
        "conversation_id": "conversation-1",
    }
    assert local_participant.publish_data.await_args.kwargs == {
        "reliable": True,
        "destination_identities": ["user-1"],
        "topic": TURN_READY_TOPIC,
    }


@pytest.mark.asyncio
async def test_ptt_release_processes_returned_transcript_once():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    transcript_future.set_result("Tolong bantu saya")
    session.commit_user_turn.return_value = transcript_future
    local_participant = MagicMock()
    local_participant.register_rpc_method = MagicMock(side_effect=lambda name: lambda fn: fn)

    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    with patch("app.voice_ptt.handle_final_transcript", new_callable=AsyncMock) as handler:
        assert json.loads(await controller.hold("user-1"))["status"] == "accepted"
        response = json.loads(await controller.release("user-1"))
        assert response == {"status": "accepted", "state": "processing"}
        await controller._pending_task

    session.commit_user_turn.assert_called_once_with(
        transcript_timeout=6.0,
        stt_flush_duration=1.5,
        skip_reply=True,
    )
    handler.assert_awaited_once_with(
        session=session,
        conversation_id="conversation-1",
        user_id="user-1",
        transcript="Tolong bantu saya",
        local_participant=local_participant,
        destination_identity="user-1",
    )
    assert controller.state == "idle"


@pytest.mark.asyncio
async def test_ptt_registered_rpc_handlers_use_verified_caller_identity():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    transcript_future.set_result("Tolong bantu saya")
    session.commit_user_turn.return_value = transcript_future
    handlers = {}

    def register_rpc_method(name):
        def decorator(fn):
            handlers[name] = fn
            return fn
        return decorator

    local_participant = MagicMock()
    local_participant.register_rpc_method.side_effect = register_rpc_method
    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )
    controller.register()

    with patch("app.voice_ptt.handle_final_transcript", new_callable=AsyncMock):
        hold_data = MagicMock(caller_identity="user-1")
        release_data = MagicMock(caller_identity="user-1")
        assert json.loads(await handlers[RPC_MIC_HOLD](hold_data))["status"] == "accepted"
        assert json.loads(await handlers[RPC_MIC_RELEASE](release_data))["status"] == "accepted"
        await controller._pending_task

    assert set(handlers) == {RPC_MIC_HOLD, RPC_MIC_RELEASE}
    session.commit_user_turn.assert_called_once()


@pytest.mark.asyncio
async def test_ptt_duplicate_release_busy_during_processing():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    session.commit_user_turn.return_value = transcript_future
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()

    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    with patch("app.voice_ptt.handle_final_transcript", new_callable=AsyncMock):
        await controller.hold("user-1")
        await controller.release("user-1")
        duplicate = json.loads(await controller.release("user-1"))
        new_hold = json.loads(await controller.hold("user-1"))
        transcript_future.set_result("Tolong bantu saya")
        await controller._pending_task

    assert duplicate == {"status": "busy", "state": "processing"}
    assert new_hold == {"status": "busy", "state": "processing"}


@pytest.mark.asyncio
async def test_ptt_rejects_unauthorized_caller():
    session = MagicMock()
    local_participant = MagicMock()
    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    assert json.loads(await controller.hold("user-2")) == {"status": "unauthorized"}
    assert json.loads(await controller.release("user-2")) == {"status": "unauthorized"}
    session.commit_user_turn.assert_not_called()


@pytest.mark.asyncio
async def test_ptt_empty_final_transcript_no_writes():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    transcript_future.set_result("   ")
    session.commit_user_turn.return_value = transcript_future
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()

    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    with patch("app.voice_turns.andora_agent.process_turn", new_callable=AsyncMock) as process_turn:
        await controller.hold("user-1")
        await controller.release("user-1")
        await controller._pending_task

    process_turn.assert_not_awaited()
    payload = json.loads(local_participant.publish_data.await_args.args[0])
    assert payload["type"] == "andora.turn.ready"
    assert payload["reason"] == "empty_transcript"


@pytest.mark.asyncio
async def test_ptt_cleanup_cancels_pending_task():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    session.commit_user_turn.return_value = transcript_future
    local_participant = MagicMock()
    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    await controller.hold("user-1")
    await controller.release("user-1")
    await controller.cleanup()

    assert controller._pending_task is None
    assert session.input.set_audio_enabled.call_args.args == (False,)


@pytest.mark.asyncio
async def test_ptt_failure_publishes_failure_event_without_fallback_speech():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    transcript_future.set_result("Tolong bantu saya")
    session.commit_user_turn.return_value = transcript_future
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock()
    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    with patch(
        "app.voice_ptt.handle_final_transcript",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        await controller.hold("user-1")
        await controller.release("user-1")
        await controller._pending_task

    session.say.assert_not_called()
    assert json.loads(local_participant.publish_data.await_args.args[0]) == {
        "type": "andora.turn.failed",
        "conversation_id": "conversation-1",
    }


@pytest.mark.asyncio
async def test_ptt_failure_publish_error_is_handled_inside_task():
    session = MagicMock()
    session.input.set_audio_enabled = MagicMock()
    transcript_future = asyncio.Future()
    transcript_future.set_result("Tolong bantu saya")
    session.commit_user_turn.return_value = transcript_future
    local_participant = MagicMock()
    local_participant.publish_data = AsyncMock(side_effect=RuntimeError("publish failed"))
    controller = PushToTalkController(
        session=session,
        local_participant=local_participant,
        owner_identity="user-1",
        conversation_id="conversation-1",
        user_id="user-1",
    )

    with patch(
        "app.voice_ptt.handle_final_transcript",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        await controller.hold("user-1")
        await controller.release("user-1")
        await controller._pending_task

    assert controller.state == "idle"
