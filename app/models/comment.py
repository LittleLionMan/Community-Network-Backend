from datetime import datetime
from sqlalchemy import Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base
from .types import UTCDateTime


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"))

    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"))

    author: Mapped["User"] = relationship("User", back_populates="comments")
    event: Mapped["Event | None"] = relationship("Event", back_populates="comments")
    service: Mapped["Service | None"] = relationship(
        "Service", back_populates="comments"
    )

    parent: Mapped["Comment | None"] = relationship(
        "Comment", remote_side=[id], back_populates="replies"
    )
    replies: Mapped[list["Comment"]] = relationship("Comment", back_populates="parent")
