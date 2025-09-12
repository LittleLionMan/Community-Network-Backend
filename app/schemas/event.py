from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from typing import Optional, Self
from datetime import datetime, timezone
from .user import UserSummary
from ..models.enums import ParticipationStatus

class EventCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class EventCategoryRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes = True)

class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=2000)
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=300)
    max_participants: Optional[int] = Field(None, gt=0)
    category_id: int

    @field_validator('start_datetime')
    @classmethod
    def validate_start_datetime(cls, v):
        now = datetime.now(timezone.utc)

        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)

        if v <= now:
            raise ValueError('Start datetime must be in the future')
        return v

    @model_validator(mode='after')
    def validate_end_after_start(self) -> Self:
        if self.end_datetime is None:
            return self

        start = self.start_datetime
        end = self.end_datetime

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        if end <= start:
            raise ValueError('End datetime must be after start datetime')

        return self

class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=300)
    max_participants: Optional[int] = Field(None, gt=0)
    category_id: Optional[int] = None
    is_active: Optional[bool] = None

class EventSummary(BaseModel):
    id: int
    title: str
    start_datetime: datetime
    location: Optional[str] = None
    creator: UserSummary
    category: EventCategoryRead
    participant_count: int = 0

    model_config = ConfigDict(from_attributes = True)

class EventRead(BaseModel):
    id: int
    title: str
    description: str
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    location: Optional[str] = None
    max_participants: Optional[int] = None
    is_active: bool
    created_at: datetime
    creator: UserSummary
    category: EventCategoryRead
    participant_count: int = 0
    is_full: bool = False

    model_config = ConfigDict(from_attributes = True)

class EventParticipationCreate(BaseModel):
    event_id: int

class EventParticipationUpdate(BaseModel):
    status: ParticipationStatus

class EventParticipationRead(BaseModel):
    id: int
    status: ParticipationStatus
    registered_at: datetime
    status_updated_at: datetime
    user: UserSummary
    event_id: int

    model_config = ConfigDict(from_attributes = True)
