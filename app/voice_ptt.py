import asyncio
import json
import logging
import time
from typing import Any

from livekit import rtc
from livekit.agents import AgentSession

from app.voice_events import publish_turn_failed
from app.voice_turns import handle_final_transcript

RPC_MIC_HOLD = "andora.mic.hold"
RPC_MIC_RELEASE = "andora.mic.release"

logger = logging.getLogger("andora.voice")


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
