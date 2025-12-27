from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base_exchange import BaseExchangeItem


class Book(BaseExchangeItem):
    __tablename__ = "books"

    isbn_13: Mapped[str] = mapped_column(
        String(13), unique=True, nullable=False, index=True
    )
    isbn_10: Mapped[str | None] = mapped_column(String(10), index=True)

    authors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_date: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(10), default="de", nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    genres: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    offers: Mapped[list["BookOffer"]] = relationship(
        "BookOffer", back_populates="book", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_books_title", "title"),
        Index("idx_books_authors_gin", "authors", postgresql_using="gin"),
        Index("idx_books_genres_gin", "genres", postgresql_using="gin"),
        Index("idx_books_topics_gin", "topics", postgresql_using="gin"),
    )
