from pydantic import BaseModel

from app.schemas.book_offer import BookOfferRead


class PaginatedBookOfferResponse(BaseModel):
    items: list[BookOfferRead]
    total: int
    skip: int
    limit: int
    has_more: bool
