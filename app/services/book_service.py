import logging

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book
from app.models.book_offer import BookOffer
from app.models.user import User
from app.schemas.book_offer import (
    CONDITION_LABELS,
    BookOfferCreate,
    BookOfferRead,
    BookOfferUpdate,
    BookUserComment,
)
from app.schemas.user import UserSummary
from app.services.google_books_client import GoogleBooksClient
from app.services.location_service import LocationService
from app.services.open_library_client import OpenLibraryClient

logger = logging.getLogger(__name__)


class BookService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_all_user_comments(self, book_id: int) -> list[BookUserComment]:
        """Lädt alle User-Kommentare zu einem Buch (von allen Offers)"""
        query = (
            select(BookOffer)
            .where(
                BookOffer.book_id == book_id,
                BookOffer.user_comment.isnot(None),
                BookOffer.user_comment != "",
            )
            .order_by(BookOffer.created_at.desc())
        )

        result = await self.db.execute(query)
        offers_with_comments = result.scalars().all()

        comments = []
        for offer in offers_with_comments:
            if offer.owner:
                comments.append(
                    BookUserComment(
                        user=UserSummary.model_validate(offer.owner),
                        comment=offer.user_comment or "",
                        created_at=offer.created_at,
                        condition=offer.condition,
                        condition_label=CONDITION_LABELS.get(
                            offer.condition, "Unbekannt"
                        ),
                    )
                )

        return comments

    async def search_or_create_book(self, isbn: str) -> Book | None:
        cleaned_isbn = isbn.replace("-", "").replace(" ", "").strip()

        query = select(Book).where(
            or_(Book.isbn_13 == cleaned_isbn, Book.isbn_10 == cleaned_isbn)
        )
        result = await self.db.execute(query)
        existing_book = result.scalar_one_or_none()

        if existing_book:
            logger.info(f"Book found in DB: {existing_book.title}")
            return existing_book

        logger.info(f"Book not in DB, searching external APIs for ISBN: {cleaned_isbn}")

        metadata = await GoogleBooksClient.search_by_isbn(cleaned_isbn)

        if not metadata:
            logger.info("Google Books failed, trying Open Library...")
            metadata = await OpenLibraryClient.search_by_isbn(cleaned_isbn)

        if not metadata:
            logger.warning(f"No metadata found for ISBN: {cleaned_isbn}")
            return None

        new_book = Book(
            isbn_13=metadata.get("isbn_13"),
            isbn_10=metadata.get("isbn_10"),
            title=metadata.get("title"),
            description=metadata.get("description"),
            authors=metadata.get("authors", []),
            publisher=metadata.get("publisher"),
            published_date=metadata.get("published_date"),
            language=metadata.get("language", "de"),
            page_count=metadata.get("page_count"),
            categories=metadata.get("categories", []),
            cover_image_url=metadata.get("cover_image_url"),
            thumbnail_url=metadata.get("thumbnail_url"),
        )

        self.db.add(new_book)
        await self.db.commit()
        await self.db.refresh(new_book)

        logger.info(f"Created new book: {new_book.title} (ID: {new_book.id})")
        return new_book

    async def create_offer(self, user_id: int, data: BookOfferCreate) -> BookOfferRead:
        book = await self.search_or_create_book(data.isbn)
        if not book:
            raise HTTPException(
                status_code=404,
                detail="Buch-Metadaten konnten nicht gefunden werden. Bitte überprüfen Sie die ISBN.",
            )

        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

        location_lat = user.location_lat
        location_lon = user.location_lon
        location_district = user.location_district

        if data.custom_location:
            geocode_result = await LocationService.geocode_location(
                data.custom_location
            )
            if not geocode_result:
                raise HTTPException(
                    status_code=400,
                    detail="Der angegebene Standort konnte nicht gefunden werden. Bitte überprüfen Sie die Adresse.",
                )

            location_lat, location_lon = LocationService.round_coordinates(
                geocode_result["lat"], geocode_result["lon"]
            )
            location_district = geocode_result["district"]
        else:
            if not user.location_lat or not user.location_lon:
                raise HTTPException(
                    status_code=400,
                    detail="Bitte hinterlegen Sie einen Standort in Ihrem Profil oder geben Sie einen benutzerdefinierten Standort an.",
                )

        new_offer = BookOffer(
            book_id=book.id,
            owner_id=user_id,
            condition=data.condition,
            notes=data.notes,
            user_comment=data.user_comment,
            location_lat=location_lat,
            location_lon=location_lon,
            location_district=location_district,
            is_available=True,
        )

        self.db.add(new_offer)
        await self.db.commit()
        await self.db.refresh(new_offer, ["book", "owner"])

        all_comments = await self._get_all_user_comments(book.id)

        logger.info(f"Created book offer ID {new_offer.id} for user {user_id}")
        return BookOfferRead.from_db(new_offer, all_user_comments=all_comments)

    async def get_my_offers(self, user_id: int) -> list[BookOfferRead]:
        query = (
            select(BookOffer)
            .where(BookOffer.owner_id == user_id)
            .order_by(BookOffer.created_at.desc())
        )

        result = await self.db.execute(query)
        offers = result.scalars().all()

        offer_reads = []
        for offer in offers:
            all_comments = await self._get_all_user_comments(offer.book_id)
            offer_reads.append(
                BookOfferRead.from_db(offer, all_user_comments=all_comments)
            )

        return offer_reads

    async def update_offer(
        self, offer_id: int, user_id: int, data: BookOfferUpdate
    ) -> BookOfferRead:
        query = select(BookOffer).where(BookOffer.id == offer_id)
        result = await self.db.execute(query)
        offer = result.scalar_one_or_none()

        if not offer:
            raise HTTPException(status_code=404, detail="Angebot nicht gefunden")

        if offer.owner_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Sie können nur Ihre eigenen Angebote bearbeiten",
            )

        update_data = data.model_dump(exclude_unset=True)

        if "custom_location" in update_data and update_data["custom_location"]:
            geocode_result = await LocationService.geocode_location(
                update_data["custom_location"]
            )
            if not geocode_result:
                raise HTTPException(
                    status_code=400,
                    detail="Der angegebene Standort konnte nicht gefunden werden",
                )

            offer.location_lat, offer.location_lon = LocationService.round_coordinates(
                geocode_result["lat"], geocode_result["lon"]
            )
            offer.location_district = geocode_result["district"]
            update_data.pop("custom_location")

        for key, value in update_data.items():
            if hasattr(offer, key):
                setattr(offer, key, value)

        await self.db.commit()
        await self.db.refresh(offer, ["book", "owner"])

        all_comments = await self._get_all_user_comments(offer.book_id)

        logger.info(f"Updated book offer ID {offer_id}")
        return BookOfferRead.from_db(offer, all_user_comments=all_comments)

    async def delete_offer(self, offer_id: int, user_id: int) -> dict[str, str]:
        query = select(BookOffer).where(BookOffer.id == offer_id)
        result = await self.db.execute(query)
        offer = result.scalar_one_or_none()

        if not offer:
            raise HTTPException(status_code=404, detail="Angebot nicht gefunden")

        if offer.owner_id != user_id:
            raise HTTPException(
                status_code=403, detail="Sie können nur Ihre eigenen Angebote löschen"
            )

        offer.is_available = False
        await self.db.commit()

        logger.info(f"Soft-deleted book offer ID {offer_id}")
        return {"message": "Angebot erfolgreich gelöscht"}
