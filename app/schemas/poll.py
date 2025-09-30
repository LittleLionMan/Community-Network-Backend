from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from .user import UserSummary
from ..models.enums import PollType

class PollOptionCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    order_index: int

class PollOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    text: str
    order_index: int
    vote_count: int = 0

class PollCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    poll_type: PollType
    ends_at: datetime | None = None
    thread_id: int | None = None
    options: list[PollOptionCreate] = Field(..., min_length=2, max_length=10)

class PollUpdate(BaseModel):
    question: str | None = Field(None, min_length=1, max_length=500)
    is_active: bool | None = None
    ends_at: datetime | None = None

class ForumThreadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str

class PollRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    question: str
    poll_type: PollType
    is_active: bool
    ends_at: datetime | None = None
    created_at: datetime
    creator: UserSummary
    thread: ForumThreadSummary | None = None
    options: list[PollOptionRead] = []
    total_votes: int = 0

class VoteCreate(BaseModel):
    option_id: int

class VoteUpdate(BaseModel):
    option_id: int

class VoteRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    created_at: datetime
    user: UserSummary
    poll_id: int
    option_id: int
