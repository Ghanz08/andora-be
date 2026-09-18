import json
from typing import Any

from livekit import rtc

TURN_COMPLETED_TOPIC = "andora.turn.completed"
TURN_READY_TOPIC = "andora.turn.ready"
TURN_FAILED_TOPIC = "andora.turn.failed"
MAX_LIVEKIT_DATA_BYTES = 14_000


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
