from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings
from app.integrations.ninerouter import ninerouter_client
from app.integrations.supabase_client import SupabaseService


class AndoraAgent:
    """
    Simplified single agent for ANDORA voice/text conversations.
    Directly loads recent history from Supabase, formats for 9router, and returns TTS-friendly response.
    """

    async def process_turn(
        self,
        conversation_id: str,
        user_id: str,
        user_text: str,
        modality: str = "voice",
    ) -> tuple[dict, dict]:
        """
        Process a conversation turn:
        1. Save final user message
        2. Load recent bounded history
        3. Formulate prompt & call 9router
        4. Save assistant message
        5. Return (user_message, assistant_message)
        """
        conversation = await SupabaseService.get_conversation_async(conversation_id, user_id)
        if not conversation:
            raise PermissionError("Conversation not found or user is not its owner")

        user_msg = await SupabaseService.add_message_async(
            conversation_id=conversation_id,
            role="user",
            content=user_text,
            modality=modality,
        )

        history_msgs = await SupabaseService.list_messages_async(
            conversation_id=conversation_id,
            limit=settings.MAX_CONTEXT_MESSAGES,
        )

        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in history_msgs:
            if m.get("role") in ("user", "assistant"):
                llm_messages.append({"role": m["role"], "content": m["content"]})

        assistant_text = await ninerouter_client.generate_response(llm_messages)

        assistant_msg = await SupabaseService.add_message_async(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_text,
            modality=modality,
        )

        if len(history_msgs) <= 2:
            short_title = user_text[:30].strip()
            if short_title:
                await SupabaseService.update_conversation_title_async(
                    conversation_id=conversation_id,
                    title=f"Bantuan: {short_title}",
                )

        return user_msg, assistant_msg


andora_agent = AndoraAgent()
