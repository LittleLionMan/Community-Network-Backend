from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

from app.models.exchange_transaction import TransactionStatus, TransactionType


class AvailabilitySlotBase(BaseModel):
    slot_type: str = Field(default="available", pattern="^(available|blocked)$")

    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None

    specific_date: date | None = None
    specific_start: datetime | None = None
    specific_end: datetime | None = None

    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_slot_type(self) -> "AvailabilitySlotBase":
        has_recurring = all(
            [
                self.day_of_week is not None,
                self.start_time is not None,
                self.end_time is not None,
            ]
        )

        has_specific = all(
            [
                self.specific_date is not None,
                self.specific_start is not None,
                self.specific_end is not None,
            ]
        )

        if not has_recurring and not has_specific:
            raise ValueError(
                "Either recurring (day_of_week, start_time, end_time) or specific (specific_date, specific_start, specific_end) fields must be provided"
            )

        if has_recurring and has_specific:
            raise ValueError("Cannot mix recurring and specific slot types")

        if has_recurring and self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be before end_time")

        if has_specific and self.specific_start and self.specific_end:
            if self.specific_start >= self.specific_end:
                raise ValueError("specific_start must be before specific_end")

        return self


class AvailabilitySlotCreate(AvailabilitySlotBase):
    pass


class AvailabilitySlotUpdate(BaseModel):
    slot_type: str | None = Field(default=None, pattern="^(available|blocked)$")
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class AvailabilitySlotRead(AvailabilitySlotBase):
    id: int
    user_id: int
    source: str
    source_id: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class AvailabilitySlotPublic(BaseModel):
    slot_type: str
    day_of_week: int | None
    start_time: time | None
    end_time: time | None
    specific_date: date | None
    display_label: str | None
