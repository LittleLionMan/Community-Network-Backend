from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Optional profile fields
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(200))

    # System fields
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Privacy settings
    email_private: Mapped[bool] = mapped_column(Boolean, default=True)
    first_name_private: Mapped[bool] = mapped_column(Boolean, default=False)
    last_name_private: Mapped[bool] = mapped_column(Boolean, default=False)
    bio_private: Mapped[bool] = mapped_column(Boolean, default=False)
    location_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at_private: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="creator")
    participations: Mapped[List["EventParticipation"]] = relationship("EventParticipation", back_populates="user")
    services: Mapped[List["Service"]] = relationship("Service", back_populates="user")
    forum_threads: Mapped[List["ForumThread"]] = relationship("ForumThread", back_populates="creator")
    forum_posts: Mapped[List["ForumPost"]] = relationship("ForumPost", back_populates="author")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="author")
    polls: Mapped[List["Poll"]] = relationship("Poll", back_populates="creator")
    votes: Mapped[List["Vote"]] = relationship("Vote", back_populates="user")

    #Auth
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    # HINZUFÜGEN:
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
