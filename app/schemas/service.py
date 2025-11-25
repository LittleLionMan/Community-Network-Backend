from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.service import ServiceType

from .user import UserSummary


class ServiceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=10, max_length=2000)
    is_offering: bool

    meeting_locations: list[str] | None = Field(None)
    price_type: str | None = Field(None, pattern=r"^(free|paid|negotiable|exchange)$")
    price_amount: float | None = Field(None, ge=0)
    estimated_duration_hours: float | None = Field(None, ge=0.25, le=168)
    contact_method: str = Field("message", pattern=r"^(message|phone|email)$")
    response_time_hours: int | None = Field(None, ge=1, le=168)

    @field_validator("meeting_locations")
    @classmethod
    def validate_meeting_locations(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [loc.strip() for loc in v if loc.strip()]
        if len(cleaned) > 5:
            raise ValueError("Maximal 5 Treffpunkte erlaubt")
        return cleaned if cleaned else None


class ServiceUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, min_length=10, max_length=2000)
    is_offering: bool | None = None
    is_active: bool | None = None

    meeting_locations: list[str] | None = Field(None)
    price_type: str | None = Field(None, pattern=r"^(free|paid|negotiable|exchange)$")
    price_amount: float | None = Field(None, ge=0)
    estimated_duration_hours: float | None = Field(None, ge=0.25, le=168)
    contact_method: str | None = Field(None, pattern=r"^(message|phone|email)$")
    response_time_hours: int | None = Field(None, ge=1, le=168)
    is_completed: bool | None = None

    @field_validator("meeting_locations")
    @classmethod
    def validate_meeting_locations(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [loc.strip() for loc in v if loc.strip()]
        if len(cleaned) > 5:
            raise ValueError("Maximal 5 Treffpunkte erlaubt")
        return cleaned if cleaned else None


class ServiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    is_offering: bool
    created_at: datetime
    updated_at: datetime | None = None

    service_image_url: str | None = None
    view_count: int = 0
    interest_count: int = 0
    is_completed: bool = False
    price_type: str | None = None
    price_amount: float | None = None
    estimated_duration_hours: float | None = None
    service_type: ServiceType
    slug: str | None = None

    user: UserSummary


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    is_offering: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    service_image_url: str | None = None
    meeting_locations: list[str] | None = None
    view_count: int = 0
    interest_count: int = 0
    is_completed: bool = False
    completed_at: datetime | None = None

    price_type: str | None = None
    price_amount: float | None = None
    price_currency: str = "EUR"
    estimated_duration_hours: float | None = None

    contact_method: str = "message"
    response_time_hours: int | None = None
    service_type: ServiceType
    slug: str | None = None

    user: UserSummary


class ServiceInterestCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    proposed_meeting_location: str | None = Field(None, max_length=500)
    proposed_meeting_time: datetime | None = None


class ServiceInterestResponse(BaseModel):
    status: str = Field(..., pattern=r"^(accepted|declined)$")
    response_message: str | None = Field(None, max_length=500)
    agreed_meeting_location: str | None = Field(None, max_length=500)
    agreed_meeting_time: datetime | None = None


class ServiceInterestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    response_message: str | None = None

    proposed_meeting_location: str | None = None
    proposed_meeting_time: datetime | None = None
    agreed_meeting_location: str | None = None
    agreed_meeting_time: datetime | None = None

    completed_by_requester: bool = False
    completed_by_provider: bool = False
    completion_notes: str | None = None

    user: UserSummary
    conversation_id: int | None = None


class ServiceStatsRead(BaseModel):
    total_active_services: int
    services_offered: int
    services_requested: int
    market_balance: float

    services_with_images_percent: float
    services_with_locations_percent: float
    average_response_time_hours: float
    completion_rate_percent: float

    user_stats: dict[str, object] | None = None


class ServiceSearchFilters(BaseModel):
    search: str | None = Field(None, min_length=3, max_length=100)
    is_offering: bool | None = None
    price_type: str | None = Field(None, pattern=r"^(free|paid|negotiable|exchange)$")
    max_price: float | None = Field(None, ge=0)
    max_duration_hours: float | None = Field(None, ge=0.25)
    has_image: bool | None = None
    has_meeting_locations: bool | None = None
    completed_only: bool | None = None
    exclude_own: bool | None = None

    near_location: str | None = Field(None, max_length=200)
    max_distance_km: float | None = Field(None, ge=1, le=100)


class ServiceRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    is_offering: bool
    created_at: datetime
    service_image_url: str | None = None
    price_type: str | None = None
    price_amount: float | None = None
    user: UserSummary

    match_score: float | None = None
    match_reason: str | None = None


class ServiceCompletionCreate(BaseModel):
    completion_notes: str | None = Field(None, max_length=1000)
