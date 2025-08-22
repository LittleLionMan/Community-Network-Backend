from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from .user import UserSummary

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    parent_id: Optional[int] = None
    event_id: Optional[int] = None
    service_id: Optional[int] = None

class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class CommentRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    author: UserSummary
    parent_id: Optional[int] = None
    event_id: Optional[int] = None
    service_id: Optional[int] = None
    replies: List['CommentRead'] = []

    model_config = ConfigDict(from_attributes = True)

# Fix forward reference
CommentRead.model_rebuild()
