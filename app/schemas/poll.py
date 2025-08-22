from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from .user import UserSummary
from ..models.enums import PollType

class PollOptionCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    order_index: int

class PollOptionRead(BaseModel):
    id: int
    text: str
    order_index: int
    vote_count: int = 0  # Computed field

    class Config:
        from_attributes = True

class PollCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    poll_type: PollType
    ends_at: Optional[datetime] = None
    thread_id: Optional[int] = None
    options: List[PollOptionCreate] = Field(..., min_items=2, max_items=10)

class PollUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=1, max_length=500)
    is_active: Optional[bool] = None
    ends_at: Optional[datetime] = None

class PollRead(BaseModel):
    id: int
    question: str
    poll_type: PollType
    is_active: bool
    ends_at: Optional[datetime] = None
    created_at: datetime
    creator: UserSummary
    thread_id: Optional[int] = None
    options: List[PollOptionRead] = []
    total_votes: int = 0  # Computed field

    class Config:
        from_attributes = True

class VoteCreate(BaseModel):
    poll_id: int
    option_id: int

class VoteUpdate(BaseModel):
    option_id: int

class VoteRead(BaseModel):
    id: int
    created_at: datetime
    user: UserSummary
    poll_id: int
    option_id: int

    class Config:
        from_attributes = True
