# app/models/business.py - Optional enhanced models
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Float, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base
from enum import Enum

class ServiceInterest(Base):
    """Track when users express interest in services"""
    __tablename__ = "service_interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))

    user: Mapped["User"] = relationship("User")
    service: Mapped["Service"] = relationship("Service")

class ModerationAction(Base):
    """Log moderation actions for audit trail"""
    __tablename__ = "moderation_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(50))  # 'flagged', 'approved', 'deleted'
    reason: Mapped[Optional[str]] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float)
    automated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    moderator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))


    content_type: Mapped[str] = mapped_column(String(50))
    content_id: Mapped[int] = mapped_column(Integer)

    moderator: Mapped[Optional["User"]] = relationship("User")

class UserEngagement(Base):
    """Track user engagement metrics"""
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
    """Daily platform statistics"""
    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)

    # Platform metrics
    active_users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    events_created: Mapped[int] = mapped_column(Integer, default=0)
    services_posted: Mapped[int] = mapped_column(Integer, default=0)
    comments_posted: Mapped[int] = mapped_column(Integer, default=0)
    polls_created: Mapped[int] = mapped_column(Integer, default=0)

    # Moderation metrics
    content_flagged: Mapped[int] = mapped_column(Integer, default=0)
    content_approved: Mapped[int] = mapped_column(Integer, default=0)
    content_removed: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
