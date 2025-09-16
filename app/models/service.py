from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .comment import Comment
    # from .business import ServiceInterest

class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_offering: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    service_image_url: Mapped[Optional[str]] = mapped_column(String(500))
    meeting_locations: Mapped[Optional[List[str]]] = mapped_column(JSON)

    view_count: Mapped[int] = mapped_column(Integer, default=0)
    interest_count: Mapped[int] = mapped_column(Integer, default=0)

    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    price_type: Mapped[Optional[str]] = mapped_column(String(50))
    price_amount: Mapped[Optional[float]] = mapped_column()
    price_currency: Mapped[str] = mapped_column(String(3), default='EUR')

    estimated_duration_hours: Mapped[Optional[float]] = mapped_column()

    contact_method: Mapped[str] = mapped_column(String(50), default='message')
    response_time_hours: Mapped[Optional[int]] = mapped_column()

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship("User", back_populates="services")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="service")
    # interests: Mapped[List["ServiceInterest"]] = relationship("ServiceInterest", back_populates="service")
