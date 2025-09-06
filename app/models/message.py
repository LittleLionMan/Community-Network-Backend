from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

if TYPE_CHECKING:
    from .user import User

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_message_preview: Mapped[Optional[str]] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    participants: Mapped[List["ConversationParticipant"]] = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_conversations_active', 'is_active'),
        Index('idx_conversations_last_message', 'last_message_at'),
    )

class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="participants")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index('idx_participants_user_conversation', 'user_id', 'conversation_id'),
        Index('idx_participants_user_active', 'user_id', 'is_archived'),
    )

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    moderation_status: Mapped[Optional[str]] = mapped_column(String(20))
    moderation_reason: Mapped[Optional[str]] = mapped_column(Text)
    moderated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    moderated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    reply_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("messages.id"))

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    moderator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[moderated_by])
    reply_to: Mapped[Optional["Message"]] = relationship("Message", remote_side=[id])
    read_receipts: Mapped[List["MessageReadReceipt"]] = relationship("MessageReadReceipt", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_messages_conversation_created', 'conversation_id', 'created_at'),
        Index('idx_messages_sender', 'sender_id'),
        Index('idx_messages_moderation', 'moderation_status', 'is_flagged'),
        Index('idx_messages_not_deleted', 'is_deleted', 'created_at'),
    )

class MessageReadReceipt(Base):
    __tablename__ = "message_read_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped["Message"] = relationship("Message", back_populates="read_receipts")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index('idx_read_receipts_unique', 'message_id', 'user_id', unique=True),
        Index('idx_read_receipts_user', 'user_id', 'read_at'),
    )
