from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from typing import Self
from datetime import datetime, timezone
from .user import UserSummary
from ..models.enums import ParticipationStatus

class EventCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)

class EventCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    name: str
    description: str | None = None

class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=2000)
    start_datetime: datetime
    end_datetime: datetime | None = None
    location: str | None = Field(None, max_length=300)
    max_participants: int | None = Field(None, gt=0)
    category_id: int | None = None

    @field_validator('start_datetime')
    @classmethod
    def validate_start_datetime(cls, v: datetime) -> datetime:
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
    title: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, min_length=1, max_length=2000)
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    location: str | None = Field(None, max_length=300)
    max_participants: int | None = Field(None, gt=0)
    category_id: int | None = None
    is_active: bool | None = None

class EventSummary(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    title: str
    start_datetime: datetime
    location: str | None = None
    creator: UserSummary
    category: EventCategoryRead | None = None
    participant_count: int = 0


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    title: str
    description: str
    start_datetime: datetime
    end_datetime: datetime | None = None
    location: str | None = None
    max_participants: int | None = None
    is_active: bool
    created_at: datetime
    creator: UserSummary
    category: EventCategoryRead
    participant_count: int = 0
    is_full: bool = False


class EventParticipationCreate(BaseModel):
    event_id: int

class EventParticipationUpdate(BaseModel):
    status: ParticipationStatus

class EventParticipationRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: int
    status: ParticipationStatus
    registered_at: datetime
    status_updated_at: datetime
    user: UserSummary
    event_id: int
