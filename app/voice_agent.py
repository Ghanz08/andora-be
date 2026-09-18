import asyncio
import json
import logging
import os
import time
from typing import Any

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    JobContext,
    RoomInputOptions,
    StopResponse,
    TurnHandlingOptions,
    cli,
    inference,
    stt,
)

RPC_MIC_HOLD = "andora.mic.hold"
RPC_MIC_RELEASE = "andora.mic.release"
TURN_COMPLETED_TOPIC = "andora.turn.completed"
TURN_READY_TOPIC = "andora.turn.ready"
TURN_FAILED_TOPIC = "andora.turn.failed"
MAX_LIVEKIT_DATA_BYTES = 14_000

from app.agent.agent import andora_agent
from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from app.integrations.faster_whisper import FasterWhisperSTT
from app.integrations.ninerouter import AssistantGenerationError, ninerouter_client
from app.integrations.supabase_client_client import SupabaseService
from app.agent.tools.search_knowledge import search_knowledge

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


def resolve_voice_context(
    room_name: str,
    user_id: str,
    is_fake_job: bool,
) -> tuple[str | None, str]:
    if is_fake_job:
        return None, user_id
    return conversation_id_from_room(room_name), user_id


def create_stt():
    whisper = FasterWhisperSTT(
        model_name=settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        language=settings.WHISPER_LANGUAGE,
    )
    return stt.StreamAdapter(stt=whisper, vad=inference.VAD())


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


def _turn_payload(
    conversation_id: str,
    user_message: dict[str, Any],
    assistant_message: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "andora.turn.completed",
        "conversation_id": conversation_id,
        "user_message": user_message,
        "assistant_message": assistant_message,
    }


async def publish_turn_completed(
    local_participant: rtc.LocalParticipant,
    destination_identity: str,
    conversation_id: str,
    user_message: dict[str, Any],
    assistant_message: dict[str, Any],
) -> None:
    payload = _turn_payload(conversation_id, user_message, assistant_message)
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_LIVEKIT_DATA_BYTES:
        payload = {
            "type": "andora.turn.completed.fetch_required",
            "conversation_id": conversation_id,
            "user_message_id": user_message.get("id"),
            "assistant_message_id": assistant_message.get("id"),
            "messages_url": f"/conversations/{conversation_id}",
        }
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    await local_participant.publish_data(
        encoded,
        reliable=True,
        destination_identities=[destination_identity],
        topic=TURN_COMPLETED_TOPIC,
    )


async def publish_turn_ready(
    local_participant: rtc.LocalParticipant,
    destination_identity: str,
    conversation_id: str,
    reason: str | None = None,
) -> None:
    payload = {
        "type": "andora.turn.ready",
        "conversation_id": conversation_id,
    }
    if reason:
        payload["reason"] = reason
    await local_participant.publish_data(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        reliable=True,
        destination_identities=[destination_identity],
        topic=TURN_READY_TOPIC,
    )


async def publish_turn_failed(
    local_participant: rtc.LocalParticipant,
    destination_identity: str,
    conversation_id: str,
) -> None:
    payload = json.dumps(
        {"type": "andora.turn.failed", "conversation_id": conversation_id},
        separators=(",", ":"),
    )
    await local_participant.publish_data(
        payload,
        reliable=True,
        destination_identities=[destination_identity],
        topic=TURN_FAILED_TOPIC,
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


class PersistenceAgent(Agent):
    def __init__(
        self,
        conversation_id: str | None,
        user_id: str,
        console_history: list[dict[str, str]],
    ) -> None:
        super().__init__(instructions=SYSTEM_PROMPT,tools=[search_knowledge] ,llm=None )
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._console_history = console_history

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        if self._conversation_id is not None:
            raise StopResponse()
        try:
            await handle_completed_turn(
                session=self.session,
                transcript=new_message.text_content,
                conversation_id=self._conversation_id,
                user_id=self._user_id,
                console_history=self._console_history,
            )
        except RuntimeError as error:
            if "AgentSession is closing" not in str(error):
                raise
            logger.info("Voice response skipped because session is closing")
        except Exception:
            logger.exception("Voice turn failed")
            self.session.say(
                "Maaf, terjadi kendala. Silakan coba lagi.",
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
        raise StopResponse()


class PushToTalkController:
    def __init__(
        self,
        *,
        session: AgentSession,
        local_participant: rtc.LocalParticipant,
        owner_identity: str,
        conversation_id: str,
        user_id: str,
    ) -> None:
        self.session = session
        self.local_participant = local_participant
        self.owner_identity = owner_identity
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.state = "idle"
        self._recording_started_at: float | None = None
        self._lock = asyncio.Lock()
        self._pending_task: asyncio.Task[None] | None = None

    def register(self) -> None:
        if self.session.input.audio is None:
            logger.warning(
                "PTT register: audio stream not attached to session.input — "
                "check RoomInputOptions(audio_enabled) and participant track publish timing"
            )
        else:
            logger.info("PTT register: audio stream attached, disabling until hold")
        self.session.input.set_audio_enabled(False)

        @self.local_participant.register_rpc_method(RPC_MIC_HOLD)
        async def on_mic_hold(data: rtc.RpcInvocationData) -> str:
            return await self.hold(data.caller_identity)

        @self.local_participant.register_rpc_method(RPC_MIC_RELEASE)
        async def on_mic_release(data: rtc.RpcInvocationData) -> str:
            return await self.release(data.caller_identity)

    async def hold(self, caller_identity: str) -> str:
        if caller_identity != self.owner_identity:
            return _rpc_response("unauthorized")
        async with self._lock:
            if self.state != "idle":
                return _rpc_response("busy", state=self.state)
            self.session.clear_user_turn()
            audio_stream = self.session.input.audio
            logger.info(
                "PTT hold: enabling audio input",
                extra={
                    "audio_stream_attached": audio_stream is not None,
                    "audio_stream_type": type(audio_stream).__name__ if audio_stream else None,
                },
            )
            self.session.input.set_audio_enabled(True)
            self._recording_started_at = time.monotonic()
            self.state = "recording"
            return _rpc_response("accepted", state=self.state)

    async def release(self, caller_identity: str) -> str:
        if caller_identity != self.owner_identity:
            return _rpc_response("unauthorized")
        async with self._lock:
            if self.state != "recording":
                return _rpc_response("busy", state=self.state)
            self.session.input.set_audio_enabled(False)
            held_seconds = (
                round(time.monotonic() - self._recording_started_at, 3)
                if self._recording_started_at is not None
                else None
            )
            logger.info(
                "Committing push-to-talk audio",
                extra={"conversation_id": self.conversation_id, "held_seconds": held_seconds},
            )
            self.state = "processing"
            try:
                transcript_future = self.session.commit_user_turn(
                    transcript_timeout=6.0,
                    stt_flush_duration=1.5,
                    skip_reply=True,
                )
            except RuntimeError as error:
                self.state = "idle"
                return _rpc_response("rejected", reason=str(error))
            self._pending_task = asyncio.create_task(self._process_committed_turn(transcript_future))
            return _rpc_response("accepted", state=self.state)

    async def _process_committed_turn(self, transcript_future: asyncio.Future[str]) -> None:
        try:
            transcript = await transcript_future
            logger.info(
                "Push-to-talk transcript committed",
                extra={
                    "conversation_id": self.conversation_id,
                    "transcript_length": len(transcript.strip()),
                },
            )
            await handle_final_transcript(
                session=self.session,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                transcript=transcript,
                local_participant=self.local_participant,
                destination_identity=self.owner_identity,
            )
        except asyncio.CancelledError:
            raise
        except RuntimeError as error:
            if "AgentSession is closing" not in str(error):
                logger.exception("Voice turn failed", extra={"conversation_id": self.conversation_id})
                await self._publish_failure()
        except Exception:
            logger.exception("Voice turn failed", extra={"conversation_id": self.conversation_id})
            await self._publish_failure()
        finally:
            self.session.input.set_audio_enabled(False)
            self._recording_started_at = None
            self.state = "idle"
            self._pending_task = None

    async def _publish_failure(self) -> None:
        try:
            await publish_turn_failed(
                local_participant=self.local_participant,
                destination_identity=self.owner_identity,
                conversation_id=self.conversation_id,
            )
        except Exception:
            logger.exception("Failed to publish voice failure event", extra={"conversation_id": self.conversation_id})

    async def cleanup(self) -> None:
        self.session.input.set_audio_enabled(False)
        self._recording_started_at = None
        if self._pending_task and not self._pending_task.done():
            pending_task = self._pending_task
            pending_task.cancel()
            try:
                await pending_task
            except asyncio.CancelledError:
                pass
            self._pending_task = None


def _rpc_response(status: str, **extra: Any) -> str:
    return json.dumps({"status": status, **extra}, separators=(",", ":"))


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
        stt=create_stt(),
        tts=inference.TTS(
            settings.LIVEKIT_TTS_MODEL,
            voice=settings.LIVEKIT_TTS_VOICE,
            language="id",
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            conn_options=APIConnectOptions(timeout=30.0, max_retry=2, retry_interval=1.0),
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection="manual" if not ctx.is_fake_job() else "stt",
        ),
    )
    console_history: list[dict[str, str]] = []

    agent = PersistenceAgent(
        conversation_id=conversation_id,
        user_id=user_id,
        console_history=console_history,
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

    controller: PushToTalkController | None = None
    if not ctx.is_fake_job():
        controller = PushToTalkController(
            session=session,
            local_participant=ctx.room.local_participant,
            owner_identity=user_id,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        controller.register()
        ctx.add_shutdown_callback(controller.cleanup)

    try:
        await play_startup_greeting(session)
    except Exception:
        logger.warning("Startup greeting TTS failed; push-to-talk remains available", exc_info=True)


if __name__ == "__main__":
    cli.run_app(server)
