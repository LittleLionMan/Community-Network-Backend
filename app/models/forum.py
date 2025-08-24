from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base
from .user import User
from .poll import Poll

class ForumThread(Base):
    __tablename__ = "forum_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Foreign Keys
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Relationships
    creator: Mapped["User"] = relationship("User", back_populates="forum_threads")
    posts: Mapped[List["ForumPost"]] = relationship("ForumPost", back_populates="thread")
    polls: Mapped[List["Poll"]] = relationship("Poll", back_populates="thread")

class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Foreign Keys
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    thread_id: Mapped[int] = mapped_column(ForeignKey("forum_threads.id"))

    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="forum_posts")
    thread: Mapped["ForumThread"] = relationship("ForumThread", back_populates="posts")
