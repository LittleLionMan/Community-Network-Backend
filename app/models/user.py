from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

if TYPE_CHECKING:
    from .event import Event, EventParticipation
    from .service import Service
    from .forum import ForumThread, ForumPost
    from .poll import Poll, Vote
    from .comment import Comment
    from .message import Message, MessageReadReceipt, ConversationParticipant

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(200))
    profile_image_url: Mapped[Optional[str]] = mapped_column(String(500))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    email_private: Mapped[bool] = mapped_column(Boolean, default=True)
    first_name_private: Mapped[bool] = mapped_column(Boolean, default=False)
    last_name_private: Mapped[bool] = mapped_column(Boolean, default=False)
    bio_private: Mapped[bool] = mapped_column(Boolean, default=False)
    location_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at_private: Mapped[bool] = mapped_column(Boolean, default=False)
    messages_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    messages_from_strangers: Mapped[bool] = mapped_column(Boolean, default=True)
    messages_notifications: Mapped[bool] = mapped_column(Boolean, default=True)

    email_notifications_events: Mapped[bool] = mapped_column(Boolean, default=True)
    email_notifications_messages: Mapped[bool] = mapped_column(Boolean, default=False)
    email_notifications_newsletter: Mapped[bool] = mapped_column(Boolean, default=False)

    events: Mapped[List["Event"]] = relationship("Event", back_populates="creator")
    participations: Mapped[List["EventParticipation"]] = relationship("EventParticipation", back_populates="user")
    services: Mapped[List["Service"]] = relationship("Service", back_populates="user")
    forum_threads: Mapped[List["ForumThread"]] = relationship("ForumThread", back_populates="creator")
    forum_posts: Mapped[List["ForumPost"]] = relationship("ForumPost", back_populates="author")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="author")
    polls: Mapped[List["Poll"]] = relationship("Poll", back_populates="creator")
    votes: Mapped[List["Vote"]] = relationship("Vote", back_populates="user")
    sent_messages: Mapped[List["Message"]] = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    conversation_participants: Mapped[List["ConversationParticipant"]] = relationship("ConversationParticipant", back_populates="user")
    moderated_messages: Mapped[List["Message"]] = relationship("Message", foreign_keys="Message.moderated_by", back_populates="moderator")
    read_receipts: Mapped[List["MessageReadReceipt"]] = relationship("MessageReadReceipt", back_populates="user")

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
