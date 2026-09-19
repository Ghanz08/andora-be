import os

from livekit.agents import AgentServer, AgentSession, JobContext, RoomInputOptions, TurnHandlingOptions, cli

from app.config import settings
from app.integrations.supabase_client import SupabaseService
from app.voice_context import conversation_id_from_room, resolve_voice_context
from app.voice_events import (
    TURN_COMPLETED_TOPIC,
    TURN_FAILED_TOPIC,
    TURN_READY_TOPIC,
    publish_turn_completed,
    publish_turn_failed,
    publish_turn_ready,
)
from app.voice_models import create_realtime_model
from app.voice_ptt import RPC_MIC_HOLD, RPC_MIC_RELEASE, PushToTalkController
from app.voice_realtime import wire_realtime_persistence
from app.voice_session_agent import PersistenceAgent
from app.voice_turns import (
    handle_completed_turn,
    handle_console_transcript,
    handle_final_transcript,
    play_startup_greeting,
)

os.environ.setdefault("LIVEKIT_URL", settings.LIVEKIT_URL)
os.environ.setdefault("LIVEKIT_API_KEY", settings.LIVEKIT_API_KEY)
os.environ.setdefault("LIVEKIT_API_SECRET", settings.LIVEKIT_API_SECRET)

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    if ctx.is_fake_job():
        conversation_id, user_id = resolve_voice_context(
            room_name=ctx.room.name,
            user_id="console-user",
            is_fake_job=True,
        )
    else:
        participant = await ctx.wait_for_participant()
        conversation_id, user_id = resolve_voice_context(
            room_name=ctx.room.name,
            user_id=participant.identity,
            is_fake_job=False,
        )
        conversation = await SupabaseService.get_conversation_async(conversation_id, user_id)
        if not conversation:
            raise PermissionError("Conversation not found or participant is not its owner")

    session = AgentSession(
        turn_handling=TurnHandlingOptions(turn_detection=None),
        userdata={"generated_documents": {}},
    )
    console_history: list[dict[str, str]] = []

    agent = PersistenceAgent(
        conversation_id=conversation_id,
        user_id=user_id,
        console_history=console_history,
        local_participant=None if ctx.is_fake_job() else ctx.room.local_participant,
        destination_identity=None if ctx.is_fake_job() else user_id,
        realtime=True,
    )
    wire_realtime_persistence(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        local_participant=None if ctx.is_fake_job() else ctx.room.local_participant,
        destination_identity=None if ctx.is_fake_job() else user_id,
    )

    if ctx.is_fake_job():
        await session.start(agent=agent, room=ctx.room)
    else:
        await session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                participant_identity=user_id,
            ),
        )


__all__ = [
    "PersistenceAgent",
    "PushToTalkController",
    "RPC_MIC_HOLD",
    "RPC_MIC_RELEASE",
    "TURN_COMPLETED_TOPIC",
    "TURN_FAILED_TOPIC",
    "TURN_READY_TOPIC",
    "conversation_id_from_room",
    "create_realtime_model",
    "handle_completed_turn",
    "handle_console_transcript",
    "handle_final_transcript",
    "play_startup_greeting",
    "publish_turn_completed",
    "publish_turn_ready",
    "publish_turn_failed",
    "resolve_voice_context",
    "wire_realtime_persistence",
]


if __name__ == "__main__":
    cli.run_app(server)
