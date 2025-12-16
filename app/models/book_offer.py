from datetime import datetime
from enum import Enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_exchange import BaseExchangeOffer
from .types import UTCDateTime


class BookCondition(str, Enum):
    NEW = "new"
    LIKE_NEW = "like_new"
    GOOD = "good"
    ACCEPTABLE = "acceptable"


class BookOffer(BaseExchangeOffer):
    __tablename__ = "book_offers"

    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    condition: Mapped[BookCondition] = mapped_column(
        SQLEnum(BookCondition, native_enum=False, length=20), nullable=False
    )

    user_comment: Mapped[str | None] = mapped_column(Text)
    exact_address: Mapped[str | None] = mapped_column(String(500))
    custom_cover_image_url: Mapped[str | None] = mapped_column(String(500))

    reserved_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reserved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )

    book: Mapped["Book"] = relationship("Book", back_populates="offers")
    owner: Mapped["User"] = relationship(
        "User", foreign_keys=[owner_id], back_populates="book_offers_owned"
    )
    reserved_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[reserved_by_user_id],
        back_populates="book_offers_reserved",
    )

    __table_args__ = (
        Index("idx_book_offers_owner", "owner_id"),
        Index("idx_book_offers_location_coords", "location_lat", "location_lon"),
        Index("idx_book_offers_book", "book_id"),
        Index("idx_book_offers_created", "created_at"),
        Index("idx_book_offers_available", "is_available"),
    )
