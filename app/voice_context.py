ROOM_PREFIX = "andora-"


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
