from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.exchange_transaction import TransactionStatus, TransactionType


class TransactionCreate(BaseModel):
    offer_type: str = Field(..., max_length=30)
    offer_id: int = Field(..., gt=0)
    transaction_type: TransactionType = TransactionType.BOOK_EXCHANGE
    initial_message: str = Field(..., min_length=1, max_length=2000)
    proposed_times: list[datetime] = Field(default_factory=list, max_length=5)

    @field_validator("proposed_times")
    @classmethod
    def validate_proposed_times(cls, v: list[datetime]) -> list[datetime]:
        if not v:
            return v

        now = datetime.now(timezone.utc)

        future_times = []
        for t in v:
            if t.tzinfo is None:
                t_aware = t.replace(tzinfo=timezone.utc)
            else:
                t_aware = t

            if t_aware > now:
                future_times.append(t_aware)

        if not future_times and v:
            raise ValueError("All proposed times must be in the future")

        return future_times


class ProposeTimeRequest(BaseModel):
    proposed_times: list[datetime] = Field(default_factory=list, max_length=5)

    @field_validator("proposed_times")
    @classmethod
    def validate_proposed_times(cls, v: list[datetime]) -> list[datetime]:
        if not v:
            return v

        now = datetime.now(timezone.utc)

        future_times = []
        for t in v:
            if t.tzinfo is None:
                t_aware = t.replace(tzinfo=timezone.utc)
            else:
                t_aware = t

            if t_aware > now:
                future_times.append(t_aware)

        if not future_times and v:
            raise ValueError("All proposed times must be in the future")

        return future_times


class UpdateAddressRequest(BaseModel):
    exact_address: str = Field(..., min_length=1, max_length=500)
    location_district: str | None = Field(None, max_length=200)


class ConfirmTimeRequest(BaseModel):
    confirmed_time: str
    exact_address: str = Field(..., min_length=1, max_length=500)

    @field_validator("confirmed_time")
    @classmethod
    def validate_confirmed_time(cls, v: str) -> str:
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            if dt <= now:
                raise ValueError("Confirmed time must be in the future")

            return v
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid datetime format: {e}")


class ConfirmHandoverRequest(BaseModel):
    pass


class CancelTransactionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class TransactionOfferInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    thumbnail_url: str | None = None
    condition: str | None = None


class TransactionParticipantInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    avatar_url: str | None = None


class TransactionData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    transaction_type: TransactionType
    status: TransactionStatus
    offer: TransactionOfferInfo
    requester: TransactionParticipantInfo
    provider: TransactionParticipantInfo
    proposed_times: list[str]
    confirmed_time: str | None = None
    exact_address: str | None = None
    location_district: str | None = None
    requester_confirmed: bool
    provider_confirmed: bool
    created_at: datetime
    expires_at: datetime | None = None
    can_propose_time: bool
    can_confirm_time: bool
    can_edit_address: bool
    can_confirm_handover: bool
    can_cancel: bool


class TransactionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    transaction_type: TransactionType
    status: TransactionStatus
    offer_title: str
    offer_thumbnail: str | None = None
    counterpart_name: str
    counterpart_avatar: str | None = None
    created_at: datetime
    confirmed_time: str | None = None
