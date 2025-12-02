from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .types import UTCDateTime


class UserAvailability(Base):
    __tablename__ = "user_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    slot_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available"
    )

    day_of_week: Mapped[int | None] = mapped_column(Integer)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)

    specific_date: Mapped[date | None] = mapped_column(Date)
    specific_start: Mapped[datetime | None] = mapped_column(UTCDateTime)
    specific_end: Mapped[datetime | None] = mapped_column(UTCDateTime)

    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_id: Mapped[int | None] = mapped_column(Integer)

    title: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(500))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="availability_slots")

    __table_args__ = (
        Index("idx_availability_user", "user_id", "is_active"),
        Index("idx_availability_date", "specific_date"),
        Index("idx_availability_source", "source", "source_id"),
    )
