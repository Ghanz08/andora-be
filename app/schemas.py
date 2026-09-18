from datetime import datetime
from pydantic import BaseModel, Field


# User
class UserAuth(BaseModel):
    id: str
    email: str | None = None
    provider: str | None = None


# Messages
class MessageBase(BaseModel):
    role: str
    content: str
    modality: str = "voice"


class MessageCreate(BaseModel):
    content: str
    modality: str = "voice"


class MessageResponse(MessageBase):
    id: str
    conversation_id: str
    created_at: datetime


# Conversations
class ConversationCreate(BaseModel):
    title: str | None = "Percakapan Baru"


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = []


# LiveKit
class LiveKitTokenRequest(BaseModel):
    conversation_id: str


class LiveKitTokenResponse(BaseModel):
    server_url: str
    participant_token: str
    room_name: str
    conversation_id: str


# Chat turn (voice STT final or text message)
class ChatTurnRequest(BaseModel):
    content: str
    modality: str = "voice"


class ChatTurnResponse(BaseModel):
    conversation_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
