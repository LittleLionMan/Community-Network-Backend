from datetime import datetime
from typing import TYPE_CHECKING, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from app.models.book_offer import BookOffer

from app.models.book_offer import BookCondition
from app.schemas.book import BookRead
from app.schemas.user import UserSummary

CONDITION_LABELS: dict[BookCondition, str] = {
    BookCondition.NEW: "Neu",
    BookCondition.LIKE_NEW: "Wie neu",
    BookCondition.GOOD: "Gut",
    BookCondition.ACCEPTABLE: "Akzeptabel",
}


class BookUserComment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserSummary
    comment: str
    created_at: datetime
    condition: BookCondition
    condition_label: str


class _BookOfferSummaryData(TypedDict):
    id: int
    condition: BookCondition
    condition_label: str | None
    is_available: bool
    created_at: datetime


class _BookOfferReadData(TypedDict):
    id: int
    book_id: int
    owner_id: int
    condition: BookCondition
    condition_label: str | None
    notes: str | None
    user_comment: str | None
    location_district: str | None
    distance_km: float | None
    is_available: bool
    created_at: datetime
    updated_at: datetime | None
    reserved_until: datetime | None
    reserved_by_user_id: int | None
    custom_cover_image_url: str | None
    book: NotRequired[BookRead | None]
    owner: NotRequired[UserSummary | None]
    all_user_comments: NotRequired[list[BookUserComment]]


class BookOfferBase(BaseModel):
    condition: BookCondition
    notes: str | None = Field(None, max_length=1000)
    user_comment: str | None = Field(
        None,
        max_length=5000,
        description="Persönliche Rezension oder Gedanken zum Buch",
    )


class BookOfferCreate(BookOfferBase):
    isbn: str = Field(..., description="ISBN-10 oder ISBN-13")
    custom_location: str | None = Field(
        None, max_length=200, description="Optional: Abweichender Standort"
    )
    location_district: str | None = Field(
        None,
        max_length=200,
        description="Stadtteil (wird automatisch vom Frontend validiert)",
    )

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, v: str) -> str:
        cleaned = v.replace("-", "").replace(" ", "").strip()

        if len(cleaned) not in (10, 13):
            raise ValueError("ISBN muss 10 oder 13 Ziffern haben")

        if not cleaned.isdigit():
            raise ValueError("ISBN darf nur Ziffern enthalten")

        return cleaned


class BookOfferUpdate(BaseModel):
    condition: BookCondition | None = None
    notes: str | None = Field(None, max_length=1000)
    user_comment: str | None = Field(None, max_length=5000)
    custom_location: str | None = Field(None, max_length=200)
    location_district: str | None = Field(
        None,
        max_length=200,
        description="Stadtteil (wird automatisch vom Frontend validiert)",
    )
    is_available: bool | None = None


class BookOfferSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    condition: BookCondition
    condition_label: str | None = None
    is_available: bool
    created_at: datetime

    @classmethod
    def from_db(cls, offer: "BookOffer") -> "BookOfferSummary":
        condition_label = CONDITION_LABELS.get(offer.condition)
        data: _BookOfferSummaryData = {
            "id": offer.id,
            "condition": offer.condition,
            "condition_label": condition_label,
            "is_available": offer.is_available,
            "created_at": offer.created_at,
        }
        return cls(**data)


class BookOfferRead(BookOfferBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    owner_id: int
    condition_label: str | None = None
    user_comment: str | None = None
    location_district: str | None = None
    distance_km: float | None = None
    is_available: bool
    created_at: datetime
    updated_at: datetime | None
    reserved_until: datetime | None
    reserved_by_user_id: int | None

    book: BookRead | None = None
    owner: UserSummary | None = None
    custom_cover_image_url: str | None = None
    all_user_comments: list[BookUserComment] = Field(
        default_factory=list,
        description="Alle User-Kommentare zu diesem Buch (von verschiedenen Angeboten)",
    )

    @classmethod
    def from_db(
        cls,
        offer: "BookOffer",
        distance_km: float | None = None,
        all_user_comments: list[BookUserComment] | None = None,
    ) -> "BookOfferRead":
        condition_label = CONDITION_LABELS.get(offer.condition)
        data: _BookOfferReadData = {
            "id": offer.id,
            "book_id": offer.book_id,
            "owner_id": offer.owner_id,
            "condition": offer.condition,
            "condition_label": condition_label,
            "notes": offer.notes,
            "user_comment": offer.user_comment,
            "location_district": offer.location_district,
            "distance_km": distance_km,
            "is_available": offer.is_available,
            "created_at": offer.created_at,
            "updated_at": offer.updated_at,
            "reserved_until": offer.reserved_until,
            "reserved_by_user_id": offer.reserved_by_user_id,
            "custom_cover_image_url": offer.custom_cover_image_url,
        }

        if offer.book:
            data["book"] = BookRead.model_validate(offer.book)

        if offer.owner:
            data["owner"] = UserSummary.model_validate(offer.owner)

        if all_user_comments:
            data["all_user_comments"] = all_user_comments

        return cls(**data)
