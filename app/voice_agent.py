import asyncio
import logging
import os

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    StopResponse,
    TurnHandlingOptions,
    UserInputTranscribedEvent,
    cli,
    inference,
)

from app.agent.agent import andora_agent
from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from app.integrations.supabase import SupabaseService

logger = logging.getLogger("andora.voice")
ROOM_PREFIX = "andora-"

os.environ.setdefault("LIVEKIT_URL", settings.LIVEKIT_URL)
os.environ.setdefault("LIVEKIT_API_KEY", settings.LIVEKIT_API_KEY)
os.environ.setdefault("LIVEKIT_API_SECRET", settings.LIVEKIT_API_SECRET)


def conversation_id_from_room(room_name: str) -> str:
    if not room_name.startswith(ROOM_PREFIX):
        raise ValueError(f"Room name must start with {ROOM_PREFIX}")
    conversation_id = room_name.removeprefix(ROOM_PREFIX).strip()
    if not conversation_id:
        raise ValueError("Room name does not contain a conversation ID")
    return conversation_id


async def handle_final_transcript(
    session: AgentSession,
    conversation_id: str,
    user_id: str,
    transcript: str,
) -> None:
    text = transcript.strip()
    if not text:
        return
    _, assistant_message = await andora_agent.process_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        user_text=text,
        modality="voice",
    )
    session.say(
        assistant_message["content"],
        allow_interruptions=True,
        add_to_chat_ctx=False,
    )


class PersistenceAgent(Agent):
    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        raise StopResponse()


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    conversation_id = conversation_id_from_room(ctx.room.name)
    participant = await ctx.wait_for_participant()
    user_id = participant.identity

    conversation = SupabaseService.get_conversation(conversation_id, user_id)
    if not conversation:
        raise PermissionError("Conversation not found or participant is not its owner")

    session = AgentSession(
        stt=inference.STT(
            settings.LIVEKIT_STT_MODEL,
            language="id",
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        ),
        tts=inference.TTS(
            settings.LIVEKIT_TTS_MODEL,
            voice=settings.LIVEKIT_TTS_VOICE,
            language="id",
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        ),
        turn_handling=TurnHandlingOptions(turn_detection="stt"),
    )
    turn_lock = asyncio.Lock()

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event: UserInputTranscribedEvent) -> None:
        if not event.is_final or not event.transcript.strip():
            return

        async def respond() -> None:
            async with turn_lock:
                try:
                    await handle_final_transcript(
                        session=session,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        transcript=event.transcript,
                    )
                except Exception:
                    logger.exception("Voice turn failed")
                    session.say(
                        "Maaf, terjadi kendala. Silakan coba lagi.",
                        allow_interruptions=True,
                        add_to_chat_ctx=False,
                    )

        asyncio.create_task(respond())

    await session.start(
        agent=PersistenceAgent(instructions=SYSTEM_PROMPT, llm=None),
        room=ctx.room,
    )
    session.say(
        "Halo, saya Andora. Apa yang bisa saya bantu?",
        allow_interruptions=True,
        add_to_chat_ctx=False,
    )


if __name__ == "__main__":
    cli.run_app(server)
