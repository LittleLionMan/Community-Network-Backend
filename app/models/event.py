from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base
from .enums import ParticipationStatus
if TYPE_CHECKING:
    from .user import User
    from .comment import Comment

class EventCategory(Base):
    __tablename__ = "event_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="category")

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    location: Mapped[Optional[str]] = mapped_column(String(300))
    max_participants: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Foreign Keys
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("event_categories.id"))

    # Relationships
    creator: Mapped["User"] = relationship("User", back_populates="events")
    category: Mapped["EventCategory"] = relationship("EventCategory", back_populates="events")
    participations: Mapped[List["EventParticipation"]] = relationship("EventParticipation", back_populates="event")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="event")

class EventParticipation(Base):
    __tablename__ = "event_participations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[ParticipationStatus] = mapped_column(SQLEnum(ParticipationStatus), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="participations")
    event: Mapped["Event"] = relationship("Event", back_populates="participations")
