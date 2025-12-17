from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import Base
from .types import UTCDateTime


class BookEnrichmentBookmark(Base):
    __tablename__ = "book_enrichment_bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_processed_book_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    books_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    books_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    google_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    openlibrary_requests: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)


class BookLastChecked(Base):
    __tablename__ = "book_last_checked"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
