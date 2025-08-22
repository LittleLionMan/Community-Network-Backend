from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Foreign Keys
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("comments.id"))  # For replies

    # Polymorphic association (comment can belong to event OR service)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id"))
    service_id: Mapped[Optional[int]] = mapped_column(ForeignKey("services.id"))

    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="comments")
    event: Mapped[Optional["Event"]] = relationship("Event", back_populates="comments")
    service: Mapped[Optional["Service"]] = relationship("Service", back_populates="comments")

    # Self-referential relationship for replies
    parent: Mapped[Optional["Comment"]] = relationship("Comment", remote_side=[id], back_populates="replies")
    replies: Mapped[List["Comment"]] = relationship("Comment", back_populates="parent")
