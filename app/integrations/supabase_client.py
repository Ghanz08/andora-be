import asyncio
from datetime import datetime, timezone
from supabase import Client, create_client
from app.config import settings

_client: Client | None = None


def get_supabase_client() -> Client:
    global _client
    if _client is None:
        key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY or "dummy_key"
        url = settings.SUPABASE_URL or "http://localhost:54321"
        _client = create_client(url, key)
    return _client


def _get_auth_provider(user) -> str | None:
    app_metadata = getattr(user, "app_metadata", None) or {}
    provider = app_metadata.get("provider")
    if provider:
        return provider

    identities = getattr(user, "identities", None) or []
    if identities:
        identity = identities[0]
        if isinstance(identity, dict):
            return identity.get("provider")
        return getattr(identity, "provider", None)

    return None


class SupabaseService:
    @staticmethod
    def get_user_from_token(token: str) -> dict | None:
        client = get_supabase_client()
        try:
            user_resp = client.auth.get_user(token)
            if user_resp and user_resp.user:
                user = user_resp.user
                return {
                    "id": user.id,
                    "email": user.email,
                    "provider": _get_auth_provider(user),
                }
        except Exception as error:
            raise ValueError("Invalid or expired token") from error
        return None

    @staticmethod
    async def get_conversation_async(conversation_id: str, user_id: str) -> dict | None:
        return await asyncio.to_thread(SupabaseService.get_conversation, conversation_id, user_id)

    @staticmethod
    async def create_conversation_async(user_id: str, title: str = "Percakapan Baru") -> dict:
        return await asyncio.to_thread(SupabaseService.create_conversation, user_id, title)

    @staticmethod
    async def list_conversations_async(user_id: str, search: str | None = None) -> list[dict]:
        return await asyncio.to_thread(SupabaseService.list_conversations, user_id, search)

    @staticmethod
    async def search_conversations_and_messages_async(user_id: str, query_str: str) -> list[dict]:
        return await asyncio.to_thread(SupabaseService.search_conversations_and_messages, user_id, query_str)

    @staticmethod
    async def list_messages_async(conversation_id: str, limit: int = 20) -> list[dict]:
        return await asyncio.to_thread(SupabaseService.list_messages, conversation_id, limit)

    @staticmethod
    async def add_message_async(
        conversation_id: str,
        role: str,
        content: str,
        modality: str = "voice",
    ) -> dict:
        return await asyncio.to_thread(
            SupabaseService.add_message,
            conversation_id,
            role,
            content,
            modality,
        )

    @staticmethod
    async def update_conversation_title_async(conversation_id: str, title: str) -> None:
        await asyncio.to_thread(SupabaseService.update_conversation_title, conversation_id, title)

    @staticmethod
    def create_conversation(user_id: str, title: str = "Percakapan Baru") -> dict:
        client = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()
        res = (
            client.table("conversations")
            .insert(
                {
                    "user_id": user_id,
                    "title": title,
                    "created_at": now,
                    "updated_at": now,
                    "last_message_at": now,
                }
            )
            .execute()
        )
        return res.data[0] if res.data else {}

    @staticmethod
    def get_conversation(conversation_id: str, user_id: str) -> dict | None:
        client = get_supabase_client()
        res = (
            client.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        return res.data[0] if res.data else None

    @staticmethod
    def list_conversations(user_id: str, search: str | None = None) -> list[dict]:
        client = get_supabase_client()
        query = (
            client.table("conversations")
            .select("*")
            .eq("user_id", user_id)
            .order("last_message_at", desc=True)
        )
        if search:
            query = query.ilike("title", f"%{search}%")
        res = query.execute()
        return res.data or []

    @staticmethod
    def search_conversations_and_messages(user_id: str, query_str: str) -> list[dict]:
        """Search across conversation title and message content for the user"""
        client = get_supabase_client()
        conv_res = (
            client.table("conversations")
            .select("*")
            .eq("user_id", user_id)
            .ilike("title", f"%{query_str}%")
            .order("last_message_at", desc=True)
            .execute()
        )
        found_convs = {c["id"]: c for c in (conv_res.data or [])}

        msg_res = (
            client.table("messages")
            .select("conversation_id, conversations!inner(user_id)")
            .eq("conversations.user_id", user_id)
            .ilike("content", f"%{query_str}%")
            .execute()
        )
        for m in msg_res.data or []:
            c_id = m.get("conversation_id")
            if c_id and c_id not in found_convs:
                conv = SupabaseService.get_conversation(c_id, user_id)
                if conv:
                    found_convs[c_id] = conv

        return sorted(
            list(found_convs.values()),
            key=lambda x: x.get("last_message_at") or "",
            reverse=True,
        )

    @staticmethod
    def list_messages(conversation_id: str, limit: int = 20) -> list[dict]:
        client = get_supabase_client()
        res = (
            client.table("messages")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        messages = res.data or []
        messages.reverse()
        return messages

    @staticmethod
    def add_message(
        conversation_id: str,
        role: str,
        content: str,
        modality: str = "voice",
    ) -> dict:
        client = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()
        res = (
            client.table("messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "role": role,
                    "content": content,
                    "modality": modality,
                    "created_at": now,
                }
            )
            .execute()
        )
        msg = res.data[0] if res.data else {}

        preview = content[:100] + ("..." if len(content) > 100 else "")
        speaker = "Andora" if role == "assistant" else "Anda"
        client.table("conversations").update(
            {
                "last_message_preview": f"{speaker}: {preview}",
                "last_message_at": now,
                "updated_at": now,
            }
        ).eq("id", conversation_id).execute()

        return msg

    @staticmethod
    def update_conversation_title(conversation_id: str, title: str):
        client = get_supabase_client()
        client.table("conversations").update({"title": title}).eq("id", conversation_id).execute()
