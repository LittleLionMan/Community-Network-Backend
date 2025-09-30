from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base
from .enums import PollType


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    poll_type: Mapped[PollType] = mapped_column(SQLEnum(PollType), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    thread_id: Mapped[int | None] = mapped_column(ForeignKey("forum_threads.id"))

    creator: Mapped["User"] = relationship("User", back_populates="polls")
    thread: Mapped["ForumThread | None"] = relationship(
        "ForumThread", back_populates="polls"
    )
    options: Mapped[list["PollOption"]] = relationship(
        "PollOption",
        back_populates="poll",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    votes: Mapped[list["Vote"]] = relationship(
        "Vote",
        back_populates="poll",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PollOption(Base):
    __tablename__ = "poll_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"))

    poll: Mapped["Poll"] = relationship("Poll", back_populates="options")
    votes: Mapped[list["Vote"]] = relationship(
        "Vote",
        back_populates="option",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"))
    option_id: Mapped[int] = mapped_column(
        ForeignKey("poll_options.id", ondelete="CASCADE")
    )

    user: Mapped["User"] = relationship("User", back_populates="votes")
    poll: Mapped["Poll"] = relationship("Poll", back_populates="votes")
    option: Mapped["PollOption"] = relationship("PollOption", back_populates="votes")
