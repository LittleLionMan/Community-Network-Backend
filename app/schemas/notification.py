from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .user import UserSummary

NotificationType = Literal[
    "forum_reply",
    "forum_mention",
    "forum_quote",
    "credit_received",
    "credit_spent",
    "service_interest",
    "service_response",
    "event_update",
    "event_cancelled",
]


class ForumNotificationData(BaseModel):
    thread_id: int
    post_id: int
    thread_title: str = Field(..., max_length=200)
    content_preview: str = Field(..., max_length=200)
    actor: UserSummary


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: NotificationType
    is_read: bool
    data: dict[str, object]
    created_at: datetime


class NotificationCreate(BaseModel):
    user_id: int
    type: NotificationType
    data: dict[str, object]


class NotificationUpdate(BaseModel):
    is_read: bool


class NotificationStats(BaseModel):
    total_unread: int
    unread_by_type: dict[str, int]
    latest_notifications: list[NotificationRead]


class NotificationPrivacySettings(BaseModel):
    forum_reply_enabled: bool = True
    forum_mention_enabled: bool = True
    forum_quote_enabled: bool = True
