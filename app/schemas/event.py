from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
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
        if v <= datetime.now():
            raise ValueError('Start datetime must be in the future')
        return v

    @field_validator('end_datetime')
    @classmethod
    def validate_end_datetime(cls, v, values):
        if v and 'start_datetime' in values and v <= values['start_datetime']:
            raise ValueError('End datetime must be after start datetime')
        return v

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
    creator_id: int
    category_id: int

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
