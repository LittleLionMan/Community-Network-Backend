from datetime import datetime
from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base


class ForumCategory(Base):
    __tablename__ = "forum_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(7))
    icon: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    threads: Mapped[list["ForumThread"]] = relationship(
        "ForumThread", back_populates="category"
    )


class ForumThread(Base):
    __tablename__ = "forum_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("forum_categories.id"))

    creator: Mapped["User"] = relationship("User", back_populates="forum_threads")
    category: Mapped["ForumCategory"] = relationship(
        "ForumCategory", back_populates="threads"
    )
    posts: Mapped[list["ForumPost"]] = relationship(
        "ForumPost",
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    polls: Mapped[list["Poll"]] = relationship(
        "Poll",
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    views = relationship(
        "ForumThreadView",
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("forum_threads.id", ondelete="CASCADE")
    )
    quoted_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("forum_posts.id", ondelete="SET NULL"), nullable=True
    )
    mentioned_user_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)

    author: Mapped["User"] = relationship("User", back_populates="forum_posts")
    thread: Mapped["ForumThread"] = relationship("ForumThread", back_populates="posts")
    quoted_post: Mapped["ForumPost | None"] = relationship(
        "ForumPost",
        remote_side="ForumPost.id",
        foreign_keys=[quoted_post_id],
        backref="quoting_posts",
    )
    has_achievement: bool = False


class ForumThreadView(Base):
    __tablename__ = "forum_thread_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("forum_threads.id", ondelete="CASCADE")
    )
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")
    thread: Mapped["ForumThread"] = relationship("ForumThread", back_populates="views")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "thread_id", name="uq_forum_thread_view_user_thread"
        ),
        Index("ix_forum_thread_views_user_id", "user_id"),
        Index("ix_forum_thread_views_thread_id", "thread_id"),
    )
