from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from .user import UserSummary

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    parent_id: int | None = None
    event_id: int | None = None
    service_id: int | None = None

class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    author: UserSummary
    parent_id: int | None = None
    event_id: int | None = None
    service_id: int | None = None
    replies: list['CommentRead'] = []

_ = CommentRead.model_rebuild()
