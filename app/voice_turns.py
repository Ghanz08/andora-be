import logging

from livekit import rtc
from livekit.agents import AgentSession

from app.agent.agent import andora_agent
from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from app.integrations.ninerouter import AssistantGenerationError, ninerouter_client
from app.voice_events import publish_turn_completed, publish_turn_failed, publish_turn_ready

logger = logging.getLogger("andora.voice")


async def handle_final_transcript(
    session: AgentSession,
    conversation_id: str,
    user_id: str,
    transcript: str,
    local_participant: rtc.LocalParticipant | None = None,
    destination_identity: str | None = None,
) -> None:
    text = transcript.strip()
    if not text:
        logger.warning(
            "Ignoring empty voice transcript",
            extra={"conversation_id": conversation_id, "destination_identity": destination_identity},
        )
        if local_participant and destination_identity:
            await publish_turn_ready(
                local_participant=local_participant,
                destination_identity=destination_identity,
                conversation_id=conversation_id,
                reason="empty_transcript",
            )
        return
    try:
        user_message, assistant_message = await andora_agent.process_turn(
            conversation_id=conversation_id,
            user_id=user_id,
            user_text=text,
            modality="voice",
        )
    except AssistantGenerationError:
        if local_participant and destination_identity:
            await publish_turn_failed(
                local_participant=local_participant,
                destination_identity=destination_identity,
                conversation_id=conversation_id,
            )
        raise
    if local_participant and destination_identity:
        await publish_turn_completed(
            local_participant=local_participant,
            destination_identity=destination_identity,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    speech = session.say(
        assistant_message["content"],
        allow_interruptions=False,
        add_to_chat_ctx=False,
    )
    await speech.wait_for_playout()
    if error := speech.exception():
        raise error
    if local_participant and destination_identity:
        await publish_turn_ready(
            local_participant=local_participant,
            destination_identity=destination_identity,
            conversation_id=conversation_id,
        )


async def handle_console_transcript(
    session: AgentSession,
    transcript: str,
    history: list[dict[str, str]],
) -> None:
    text = transcript.strip()
    if not text:
        return
    history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    try:
        assistant_text = await ninerouter_client.generate_response(messages)
    except AssistantGenerationError:
        history.pop()
        raise
    history.append({"role": "assistant", "content": assistant_text})
    del history[:-settings.MAX_CONTEXT_MESSAGES]
    speech = session.say(
        assistant_text,
        allow_interruptions=False,
        add_to_chat_ctx=False,
    )
    await speech.wait_for_playout()
    if error := speech.exception():
        raise error


async def handle_completed_turn(
    session: AgentSession,
    transcript: str,
    conversation_id: str | None,
    user_id: str,
    console_history: list[dict[str, str]],
    local_participant: rtc.LocalParticipant | None = None,
    destination_identity: str | None = None,
) -> None:
    logger.info("Processing completed voice turn", extra={"transcript_length": len(transcript)})
    if conversation_id is None:
        await handle_console_transcript(
            session=session,
            transcript=transcript,
            history=console_history,
        )
    else:
        await handle_final_transcript(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
            transcript=transcript,
            local_participant=local_participant,
            destination_identity=destination_identity,
        )
    logger.info("Voice response completed")


async def play_startup_greeting(session: AgentSession) -> None:
    greeting = session.say(
        "Halo, saya Andora. Apa yang bisa saya bantu?",
        allow_interruptions=False,
        add_to_chat_ctx=False,
    )
    await greeting.wait_for_playout()
    if error := greeting.exception():
        raise error
