from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from .user import UserSummary

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    reply_to_id: Optional[int] = None

class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

class ConversationCreate(BaseModel):
    participant_id: int
    initial_message: str = Field(..., min_length=1, max_length=2000)

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender: UserSummary
    content: str
    message_type: str
    created_at: datetime
    edited_at: Optional[datetime] = None
    is_edited: bool
    is_deleted: bool
    reply_to_id: Optional[int] = None
    reply_to: Optional["MessageResponse"] = None
    is_read: bool = False

    model_config = ConfigDict(from_attributes=True)

class ConversationParticipantResponse(BaseModel):
    user: UserSummary
    joined_at: datetime
    last_read_at: Optional[datetime] = None
    is_muted: bool
    is_archived: bool

    model_config = ConfigDict(from_attributes=True)

class ConversationResponse(BaseModel):
    id: int
    participants: List[ConversationParticipantResponse]
    last_message: Optional[MessageResponse] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationDetailResponse(BaseModel):
    id: int
    participants: List[ConversationParticipantResponse]
    messages: List[MessageResponse]
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime
    has_more: bool = False

    model_config = ConfigDict(from_attributes=True)

class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    page: int
    size: int
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    total: int
    page: int
    size: int
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

class MessageModerationResponse(BaseModel):
    id: int
    conversation_id: int
    sender: UserSummary
    content: str
    created_at: datetime
    is_flagged: bool
    moderation_status: Optional[str] = None
    moderation_reason: Optional[str] = None
    moderated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class MessageModerationAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|flag)$")
    reason: Optional[str] = Field(None, max_length=500)

class ConversationSettings(BaseModel):
    is_muted: Optional[bool] = None
    is_archived: Optional[bool] = None

class MessagePrivacySettings(BaseModel):
    messages_enabled: Optional[bool] = None
    messages_from_strangers: Optional[bool] = None
    messages_notifications: Optional[bool] = None

class UnreadCountResponse(BaseModel):
    total_unread: int
    conversations: List[dict]

class WebSocketMessageEvent(BaseModel):
    """Schema for WebSocket message events"""
    type: str
    conversation_id: int
    message: Optional[MessageResponse] = None
    user_id: Optional[int] = None
    data: Optional[dict] = None

MessageResponse.model_rebuild()
