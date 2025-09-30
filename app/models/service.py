from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_offering: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    service_image_url: Mapped[str | None] = mapped_column(String(500))
    meeting_locations: Mapped[list[str | None]] = mapped_column(JSON)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    interest_count: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped["User"] = relationship("User", back_populates="services")

    price_type: Mapped[str | None] = mapped_column(String(50))
    price_amount: Mapped[float | None] = mapped_column()
    price_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    estimated_duration_hours: Mapped[float | None] = mapped_column()
    contact_method: Mapped[str] = mapped_column(String(50), default="message")
    response_time_hours: Mapped[int | None] = mapped_column()

    admin_notes: Mapped[str | None] = mapped_column(Text)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flagged_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(Integer)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="service"
    )
