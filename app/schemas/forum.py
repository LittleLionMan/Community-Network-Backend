from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from .user import UserSummary

class ForumThreadCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)

class ForumThreadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    is_pinned: Optional[bool] = None
    is_locked: Optional[bool] = None

class ForumThreadRead(BaseModel):
    id: int
    title: str
    is_pinned: bool
    is_locked: bool
    created_at: datetime
    creator: UserSummary

    class Config:
        from_attributes = True

class ForumPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    thread_id: int

class ForumPostUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

class ForumPostRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    author: UserSummary
    thread_id: int

    class Config:
        from_attributes = True
