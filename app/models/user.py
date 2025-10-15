from datetime import datetime
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

    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    bio: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    profile_image_url: Mapped[str | None] = mapped_column(String(500))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    notification_forum_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_forum_mention: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_forum_quote: Mapped[bool] = mapped_column(Boolean, default=True)

    email_notifications_events: Mapped[bool] = mapped_column(Boolean, default=True)
    email_notifications_messages: Mapped[bool] = mapped_column(Boolean, default=False)
    email_notifications_newsletter: Mapped[bool] = mapped_column(Boolean, default=False)

    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship("Event", back_populates="creator")
    participations: Mapped[list["EventParticipation"]] = relationship(
        "EventParticipation", back_populates="user"
    )
    services: Mapped[list["Service"]] = relationship(
        "Service", back_populates="user", foreign_keys="Service.user_id"
    )
    forum_threads: Mapped[list["ForumThread"]] = relationship(
        "ForumThread", back_populates="creator"
    )
    forum_posts: Mapped[list["ForumPost"]] = relationship(
        "ForumPost", back_populates="author"
    )
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="author")
    polls: Mapped[list["Poll"]] = relationship("Poll", back_populates="creator")
    votes: Mapped[list["Vote"]] = relationship("Vote", back_populates="user")
    sent_messages: Mapped[list["Message"]] = relationship(
        "Message", foreign_keys="Message.sender_id", back_populates="sender"
    )
    conversation_participants: Mapped[list["ConversationParticipant"]] = relationship(
        "ConversationParticipant", back_populates="user"
    )
    moderated_messages: Mapped[list["Message"]] = relationship(
        "Message", foreign_keys="Message.moderated_by", back_populates="moderator"
    )
    read_receipts: Mapped[list["MessageReadReceipt"]] = relationship(
        "MessageReadReceipt", back_populates="user"
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    achievements_received: Mapped[list["UserAchievement"]] = relationship(
        "UserAchievement",
        foreign_keys="UserAchievement.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    achievements_awarded: Mapped[list["UserAchievement"]] = relationship(
        "UserAchievement",
        foreign_keys="UserAchievement.awarded_by_user_id",
        back_populates="awarded_by",
    )
