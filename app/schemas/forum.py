from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from .user import UserSummary

class ForumCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    icon: Optional[str] = Field(None, max_length=50)
    display_order: int = Field(0, ge=0)

class ForumCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    icon: Optional[str] = Field(None, max_length=50)
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

class ForumCategoryRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool
    display_order: int
    created_at: datetime
    thread_count: int = 0
    latest_thread: Optional['ForumThreadSummary'] = None

    model_config = ConfigDict(from_attributes=True)

class ForumThreadSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    creator: UserSummary

    model_config = ConfigDict(from_attributes=True)

class ForumThreadCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category_id: int

class ForumThreadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    is_pinned: Optional[bool] = None
    is_locked: Optional[bool] = None
    category_id: Optional[int] = None

class ForumThreadRead(BaseModel):
    id: int
    title: str
    is_pinned: bool
    is_locked: bool
    created_at: datetime
    creator: UserSummary
    category: ForumCategoryRead
    post_count: int = 0
    latest_post: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ForumPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

class ForumPostUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

class ForumPostRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    author: UserSummary
    thread_id: int

    model_config = ConfigDict(from_attributes=True)

ForumCategoryRead.model_rebuild()
