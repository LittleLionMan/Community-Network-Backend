from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base
if TYPE_CHECKING:
    from .user import User
    from .service import Service


class ServiceInterest(Base):
    __tablename__ = "service_interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(50), default='pending')
    response_message: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    proposed_meeting_location: Mapped[str | None] = mapped_column(String(500))
    proposed_meeting_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agreed_meeting_location: Mapped[str | None] = mapped_column(String(500))
    agreed_meeting_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    completed_by_requester: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_by_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    completion_notes: Mapped[str | None] = mapped_column(Text)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))

class ServiceTag(Base):
    __tablename__ = "service_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ModerationAction(Base):
    __tablename__ = "moderation_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(default=1.0)
    automated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    content_type: Mapped[str] = mapped_column(String(50))
    content_id: Mapped[int] = mapped_column(Integer)

    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ServiceTagAssociation(Base):
    __tablename__ = "service_tag_associations"

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("service_tags.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    service: Mapped["Service"] = relationship("Service")
    tag: Mapped["ServiceTag"] = relationship("ServiceTag")

class UserEngagement(Base):
    __tablename__ = "user_engagement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)

    events_created: Mapped[int] = mapped_column(Integer, default=0)
    events_joined: Mapped[int] = mapped_column(Integer, default=0)
    services_posted: Mapped[int] = mapped_column(Integer, default=0)
    comments_made: Mapped[int] = mapped_column(Integer, default=0)
    polls_created: Mapped[int] = mapped_column(Integer, default=0)
    votes_cast: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    user: Mapped["User"] = relationship("User")

class DailyStats(Base):
    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)

    active_users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    events_created: Mapped[int] = mapped_column(Integer, default=0)
    services_posted: Mapped[int] = mapped_column(Integer, default=0)
    comments_posted: Mapped[int] = mapped_column(Integer, default=0)
    polls_created: Mapped[int] = mapped_column(Integer, default=0)

    content_flagged: Mapped[int] = mapped_column(Integer, default=0)
    content_approved: Mapped[int] = mapped_column(Integer, default=0)
    content_removed: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
