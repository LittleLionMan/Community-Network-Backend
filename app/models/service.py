from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base
from .types import UTCDateTime


class ServiceType(str, Enum):
    user_service = "user_service"
    platform_feature = "platform_feature"

    def __str__(self):
        return self.value


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_offering: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, onupdate=func.now()
    )

    service_type: Mapped[ServiceType] = mapped_column(
        SQLEnum(ServiceType, native_enum=True, name="servicetype"),
        default=ServiceType.USER_SERVICE,
        nullable=False,
        index=True,
    )
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)

    service_image_url: Mapped[str | None] = mapped_column(String(500))
    meeting_locations: Mapped[list[str | None]] = mapped_column(JSON)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    interest_count: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    price_type: Mapped[str | None] = mapped_column(String(50))
    price_amount: Mapped[float | None] = mapped_column()
    price_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    estimated_duration_hours: Mapped[float | None] = mapped_column()
    contact_method: Mapped[str] = mapped_column(String(50), default="message")
    response_time_hours: Mapped[int | None] = mapped_column()

    admin_notes: Mapped[str | None] = mapped_column(Text)
    flagged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    flagged_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reviewed_by: Mapped[int | None] = mapped_column(Integer)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship("User", back_populates="services")
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="service"
    )

    __table_args__ = (Index("idx_services_type_active", "service_type", "is_active"),)
