from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookBase(BaseModel):
    isbn_13: str = Field(..., min_length=13, max_length=13)
    isbn_10: str | None = Field(None, min_length=10, max_length=10)
    title: str = Field(..., max_length=300)
    description: str | None = None
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = Field(None, max_length=200)
    published_date: str | None = Field(None, max_length=50)
    language: str = Field(default="de", max_length=10)
    page_count: int | None = Field(None, ge=1)
    categories: list[str] = Field(default_factory=list)
    cover_image_url: str | None = Field(None, max_length=500)
    thumbnail_url: str | None = Field(None, max_length=500)


class BookRead(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
