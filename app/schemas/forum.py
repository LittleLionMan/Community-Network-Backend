from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import TYPE_CHECKING

from .user import UserSummary

if TYPE_CHECKING:
    pass


class ForumCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(None, max_length=50)
    display_order: int = Field(0, ge=0)


class ForumCategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(None, max_length=50)
    display_order: int | None = Field(None, ge=0)
    is_active: bool | None = None


class ForumThreadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    creator: UserSummary


class ForumCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    is_active: bool
    display_order: int
    created_at: datetime
    thread_count: int = 0
    latest_thread: ForumThreadSummary | None = None


class ForumThreadCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category_id: int


class ForumThreadUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    is_pinned: bool | None = None
    is_locked: bool | None = None
    category_id: int | None = None


class ForumThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    is_pinned: bool
    is_locked: bool
    created_at: datetime
    creator: UserSummary
    category: ForumCategoryRead
    post_count: int = 0
    latest_post: datetime | None = None


class QuotedPostSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    author: UserSummary
    thread_id: int
    quoted_post: "QuotedPostSummary | None" = None


class ForumPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    quoted_post_id: int | None = None


class ForumPostUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class ForumPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    updated_at: datetime | None = None
    author: UserSummary
    thread_id: int
    quoted_post: QuotedPostSummary | None = None
    mentioned_user_ids: list[int] | None = None
    has_achievement: bool = False


_ = ForumCategoryRead.model_rebuild()
_ = ForumThreadRead.model_rebuild()
_ = ForumPostRead.model_rebuild()
_ = QuotedPostSummary.model_rebuild()
