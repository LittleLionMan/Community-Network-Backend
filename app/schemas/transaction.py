from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TransactionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    TIME_CONFIRMED = "time_confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TransactionType(str, Enum):
    BOOK_EXCHANGE = "book_exchange"
    SERVICE_MEETUP = "service_meetup"
    EVENT_CONFIRMATION = "event_confirmation"


class TransactionCreate(BaseModel):
    offer_type: str = Field(..., description="Type of offer (e.g., 'book_offer')")
    offer_id: int = Field(..., gt=0)
    transaction_type: TransactionType
    initial_message: str = Field(..., min_length=1, max_length=2000)
    proposed_times: list[datetime] = Field(default_factory=list, max_length=5)

    @field_validator("proposed_times")
    @classmethod
    def validate_proposed_times(cls, v: list[datetime]) -> list[datetime]:
        now = datetime.now()
        future_times = [t for t in v if t > now]
        return future_times[:5]


class TransactionAccept(BaseModel):
    message: str | None = Field(None, max_length=1000)


class TransactionReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class TransactionProposeTime(BaseModel):
    proposed_time: datetime

    @field_validator("proposed_time")
    @classmethod
    def validate_future_time(cls, v: datetime) -> datetime:
        if v <= datetime.now():
            raise ValueError("Proposed time must be in the future")
        return v


class TransactionConfirmTime(BaseModel):
    confirmed_time: datetime
    exact_address: str = Field(..., min_length=5, max_length=500)

    @field_validator("confirmed_time")
    @classmethod
    def validate_future_time(cls, v: datetime) -> datetime:
        if v <= datetime.now():
            raise ValueError("Confirmed time must be in the future")
        return v


class TransactionCancel(BaseModel):
    reason: str | None = Field(None, max_length=500)


class TransactionConfirmHandover(BaseModel):
    notes: str | None = Field(None, max_length=500)


class TransactionOfferInfo(BaseModel):
    offer_id: int
    offer_type: str
    title: str
    thumbnail_url: str | None = None
    condition: str | None = None
    metadata: dict[str, str | int | bool | list[str] | None]


class TransactionParticipantInfo(BaseModel):
    id: int
    display_name: str
    profile_image_url: str | None = None


class TransactionData(BaseModel):
    transaction_id: int
    transaction_type: TransactionType
    status: TransactionStatus

    offer: TransactionOfferInfo

    requester: TransactionParticipantInfo
    provider: TransactionParticipantInfo

    proposed_times: list[datetime] = Field(default_factory=list)
    confirmed_time: datetime | None = None
    exact_address: str | None = None

    requester_confirmed: bool = False
    provider_confirmed: bool = False

    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    is_expired: bool = False
    can_accept: bool = False
    can_reject: bool = False
    can_propose_time: bool = False
    can_confirm_time: bool = False
    can_confirm_handover: bool = False
    can_cancel: bool = False

    metadata: dict[str, str | int | bool | list[str] | None] = Field(
        default_factory=dict
    )


class TransactionResponse(BaseModel):
    id: int
    message_id: int
    transaction_type: TransactionType
    status: TransactionStatus
    offer_type: str
    offer_id: int

    requester_id: int
    provider_id: int

    proposed_times: list[datetime]
    confirmed_time: datetime | None
    exact_address: str | None

    requester_confirmed_handover: bool
    provider_confirmed_handover: bool

    credit_amount: int
    credit_transferred: bool

    created_at: datetime
    accepted_at: datetime | None
    time_confirmed_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime

    metadata: dict[str, str | int | bool | list[str] | None]


class TransactionHistoryItem(BaseModel):
    id: int
    transaction_type: TransactionType
    status: TransactionStatus
    offer_title: str
    offer_thumbnail: str | None
    counterpart_name: str
    counterpart_avatar: str | None
    confirmed_time: datetime | None
    created_at: datetime
    updated_at: datetime
