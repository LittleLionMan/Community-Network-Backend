from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .user import UserSummary


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    reply_to_id: int | None = None


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class ConversationCreate(BaseModel):
    participant_id: int
    initial_message: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender: UserSummary
    content: str
    message_type: str
    created_at: datetime
    edited_at: datetime | None = None
    is_edited: bool
    is_deleted: bool
    reply_to_id: int | None = None
    reply_to: MessageResponse | None = None
    is_read: bool = False
    transaction_data: dict[str, str | int | bool | None] | None = None


class ConversationParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserSummary
    joined_at: datetime
    last_read_at: datetime | None = None
    is_muted: bool
    is_archived: bool


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    participants: list[ConversationParticipantResponse]
    last_message: MessageResponse | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    participants: list[ConversationParticipantResponse]
    messages: list[MessageResponse]
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime
    has_more: bool = False


class MessageListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    messages: list[MessageResponse]
    total: int
    page: int
    size: int
    has_more: bool


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversations: list[ConversationResponse]
    total: int
    page: int
    size: int
    has_more: bool


class MessageModerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender: UserSummary
    content: str
    created_at: datetime
    is_flagged: bool
    moderation_status: str | None = None
    moderation_reason: str | None = None
    moderated_at: datetime | None = None


class MessageModerationAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|flag)$")
    reason: str | None = Field(None, max_length=500)


class ConversationSettings(BaseModel):
    is_muted: bool | None = None
    is_archived: bool | None = None


class MessagePrivacySettings(BaseModel):
    messages_enabled: bool | None = None
    messages_from_strangers: bool | None = None
    messages_notifications: bool | None = None


class UnreadCountResponse(BaseModel):
    total_unread: int
    conversations: list[dict[str, object]]


class WebSocketMessageEvent(BaseModel):
    type: str
    conversation_id: int
    message: MessageResponse | None = None
    user_id: int | None = None
    data: dict[str, object] | None = None


_ = MessageResponse.model_rebuild()
