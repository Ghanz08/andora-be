from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_user
from app.integrations.livekit import livekit_service
from app.integrations.supabase_client import SupabaseService
from app.schemas import LiveKitTokenRequest, LiveKitTokenResponse, UserAuth

router = APIRouter(prefix="/livekit", tags=["livekit"])


@router.post("/token", response_model=LiveKitTokenResponse)
async def generate_livekit_token(
    payload: LiveKitTokenRequest,
    current_user: UserAuth = Depends(get_current_user),
):
    conversation = SupabaseService.get_conversation(
        conversation_id=payload.conversation_id,
        user_id=current_user.id,
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized",
        )

    room_name = f"andora-{payload.conversation_id}"
    token = livekit_service.create_user_token(
        user_id=current_user.id,
        user_name=current_user.email,
        room_name=room_name,
    )

    return LiveKitTokenResponse(
        server_url=livekit_service.url,
        participant_token=token,
        room_name=room_name,
        conversation_id=payload.conversation_id,
    )
