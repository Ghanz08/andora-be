import asyncio
import logging
from typing import Any

from livekit import rtc
from livekit.agents import AgentSession

from app.integrations.supabase_client import SupabaseService
from app.voice_events import publish_turn_completed, publish_turn_failed, publish_turn_ready

logger = logging.getLogger("andora.voice")


def _message_text(item: Any) -> str:
    text = getattr(item, "text_content", None)
    if isinstance(text, str):
        return text.strip()
    return ""


def wire_realtime_persistence(
    session: AgentSession,
    *,
    conversation_id: str | None,
    user_id: str,
    local_participant: rtc.LocalParticipant | None,
    destination_identity: str | None,
) -> None:
    if not conversation_id or not local_participant or not destination_identity:
        return

    state: dict[str, dict[str, Any] | None] = {"last_user_message": None}

    async def persist_item(item: Any) -> None:
        role = getattr(item, "role", None)
        if role not in {"user", "assistant"}:
            return
        text = _message_text(item)
        if not text:
            return
        if getattr(item, "interrupted", False):
            return
        try:
            if role == "user":
                conversation = await SupabaseService.get_conversation_async(conversation_id, user_id)
                if not conversation:
                    logger.warning("Skipping realtime user message for unauthorized conversation")
                    return
                state["last_user_message"] = await SupabaseService.add_message_async(
                    conversation_id=conversation_id,
                    role="user",
                    content=text,
                    modality="voice",
                )
                return

            assistant_message = await SupabaseService.add_message_async(
                conversation_id=conversation_id,
                role="assistant",
                content=text,
                modality="voice",
            )
            user_message = state.get("last_user_message")
            if user_message:
                await publish_turn_completed(
                    local_participant=local_participant,
                    destination_identity=destination_identity,
                    conversation_id=conversation_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                )
                await publish_turn_ready(
                    local_participant=local_participant,
                    destination_identity=destination_identity,
                    conversation_id=conversation_id,
                )
                state["last_user_message"] = None
        except Exception:
            logger.exception("Failed to persist realtime conversation item", extra={"conversation_id": conversation_id})
            await publish_turn_failed(
                local_participant=local_participant,
                destination_identity=destination_identity,
                conversation_id=conversation_id,
            )

    @session.on("conversation_item_added")
    def on_conversation_item_added(event: Any) -> None:
        asyncio.create_task(persist_item(event.item))
