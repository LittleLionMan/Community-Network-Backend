from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from .user import UserSummary

class ServiceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=10, max_length=2000)
    is_offering: bool

    meeting_locations: Optional[List[str]] = Field(None)
    price_type: Optional[str] = Field(None, pattern=r'^(free|paid|negotiable|exchange)$')
    price_amount: Optional[float] = Field(None, ge=0)
    estimated_duration_hours: Optional[float] = Field(None, ge=0.25, le=168)
    contact_method: str = Field('message', pattern=r'^(message|phone|email)$')
    response_time_hours: Optional[int] = Field(None, ge=1, le=168)

    @field_validator('meeting_locations')
    @classmethod
    def validate_meeting_locations(cls, v):
        if v is None:
            return v
        cleaned = [loc.strip() for loc in v if loc.strip()]
        if len(cleaned) > 5:
            raise ValueError('Maximal 5 Treffpunkte erlaubt')
        return cleaned if cleaned else None

class ServiceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=10, max_length=2000)
    is_offering: Optional[bool] = None
    is_active: Optional[bool] = None

    meeting_locations: Optional[List[str]] = Field(None)
    price_type: Optional[str] = Field(None, pattern=r'^(free|paid|negotiable|exchange)$')
    price_amount: Optional[float] = Field(None, ge=0)
    estimated_duration_hours: Optional[float] = Field(None, ge=0.25, le=168)
    contact_method: Optional[str] = Field(None, pattern=r'^(message|phone|email)$')
    response_time_hours: Optional[int] = Field(None, ge=1, le=168)
    is_completed: Optional[bool] = None

    @field_validator('meeting_locations')
    @classmethod
    def validate_meeting_locations(cls, v):
        if v is None:
            return v
        cleaned = [loc.strip() for loc in v if loc.strip()]
        if len(cleaned) > 5:
            raise ValueError('Maximal 5 Treffpunkte erlaubt')
        return cleaned if cleaned else None

class ServiceSummary(BaseModel):
    id: int
    title: str
    is_offering: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    service_image_url: Optional[str] = None
    view_count: int = 0
    interest_count: int = 0
    is_completed: bool = False
    price_type: Optional[str] = None
    price_amount: Optional[float] = None
    estimated_duration_hours: Optional[float] = None

    user: UserSummary

    model_config = ConfigDict(from_attributes=True)

class ServiceRead(BaseModel):
    id: int
    title: str
    description: str
    is_offering: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    service_image_url: Optional[str] = None
    meeting_locations: Optional[List[str]] = None
    view_count: int = 0
    interest_count: int = 0
    is_completed: bool = False
    completed_at: Optional[datetime] = None

    price_type: Optional[str] = None
    price_amount: Optional[float] = None
    price_currency: str = 'EUR'
    estimated_duration_hours: Optional[float] = None

    contact_method: str = 'message'
    response_time_hours: Optional[int] = None

    user: UserSummary

    model_config = ConfigDict(from_attributes=True)

class ServiceInterestCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    proposed_meeting_location: Optional[str] = Field(None, max_length=500)
    proposed_meeting_time: Optional[datetime] = None

class ServiceInterestResponse(BaseModel):
    status: str = Field(..., pattern=r'^(accepted|declined)$')
    response_message: Optional[str] = Field(None, max_length=500)
    agreed_meeting_location: Optional[str] = Field(None, max_length=500)
    agreed_meeting_time: Optional[datetime] = None

class ServiceInterestRead(BaseModel):
    id: int
    message: str
    status: str
    created_at: datetime
    responded_at: Optional[datetime] = None
    response_message: Optional[str] = None

    proposed_meeting_location: Optional[str] = None
    proposed_meeting_time: Optional[datetime] = None
    agreed_meeting_location: Optional[str] = None
    agreed_meeting_time: Optional[datetime] = None

    completed_by_requester: bool = False
    completed_by_provider: bool = False
    completion_notes: Optional[str] = None

    user: UserSummary
    conversation_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class ServiceStatsRead(BaseModel):
    total_active_services: int
    services_offered: int
    services_requested: int
    market_balance: float

    services_with_images_percent: float
    services_with_locations_percent: float
    average_response_time_hours: float
    completion_rate_percent: float

    user_stats: Optional[dict] = None

class ServiceSearchFilters(BaseModel):
    search: Optional[str] = Field(None, min_length=3, max_length=100)
    is_offering: Optional[bool] = None
    price_type: Optional[str] = Field(None, pattern=r'^(free|paid|negotiable|exchange)$')
    max_price: Optional[float] = Field(None, ge=0)
    max_duration_hours: Optional[float] = Field(None, ge=0.25)
    has_image: Optional[bool] = None
    has_meeting_locations: Optional[bool] = None
    completed_only: Optional[bool] = None
    exclude_own: Optional[bool] = None

    near_location: Optional[str] = Field(None, max_length=200)
    max_distance_km: Optional[float] = Field(None, ge=1, le=100)

class ServiceRecommendationRead(BaseModel):
    id: int
    title: str
    description: str
    is_offering: bool
    created_at: datetime
    service_image_url: Optional[str] = None
    price_type: Optional[str] = None
    price_amount: Optional[float] = None
    user: UserSummary

    match_score: Optional[float] = None
    match_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ServiceCompletionCreate(BaseModel):
    completion_notes: Optional[str] = Field(None, max_length=1000)
