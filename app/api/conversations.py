from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.agent.agent import andora_agent
from app.api.deps import get_current_user
from app.integrations.supabase_client import SupabaseService
from app.schemas import (
    ChatTurnRequest,
    ChatTurnResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    UserAuth,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate | None = None,
    current_user: UserAuth = Depends(get_current_user),
):
    title = (payload and payload.title) or "Percakapan Baru"
    conv = SupabaseService.create_conversation(user_id=current_user.id, title=title)
    return conv


@router.get("", response_model=list[ConversationResponse])
async def list_recent_conversations(
    search: str | None = Query(None),
    current_user: UserAuth = Depends(get_current_user),
):
    if search:
        return SupabaseService.search_conversations_and_messages(
            user_id=current_user.id,
            query_str=search,
        )
    return SupabaseService.list_conversations(user_id=current_user.id)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: str,
    current_user: UserAuth = Depends(get_current_user),
):
    conv = SupabaseService.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized",
        )
    messages = SupabaseService.list_messages(conversation_id=conversation_id)
    return {**conv, "messages": messages}


@router.post("/{conversation_id}/messages", response_model=ChatTurnResponse)
async def send_message_turn(
    conversation_id: str,
    payload: ChatTurnRequest,
    current_user: UserAuth = Depends(get_current_user),
):
    conv = SupabaseService.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized",
        )

    user_msg, assistant_msg = await andora_agent.process_turn(
        conversation_id=conversation_id,
        user_id=current_user.id,
        user_text=payload.content,
        modality=payload.modality,
    )

    return ChatTurnResponse(
        conversation_id=conversation_id,
        user_message=user_msg,
        assistant_message=assistant_msg,
    )
