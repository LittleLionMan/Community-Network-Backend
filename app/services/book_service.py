import logging

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from app.services.classification_mapping_service import ClassificationMappingService
from app.services.file_service import FileUploadService
from app.services.google_books_client import GoogleBooksClient
from app.services.location_service import LocationService
from app.services.open_library_client import OpenLibraryClient

logger = logging.getLogger(__name__)


class BookService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_all_user_comments(self, book_id: int) -> list[BookUserComment]:
        query = (
            select(BookOffer)
            .options(selectinload(BookOffer.owner))
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

            needs_enrichment = (
                not existing_book.cover_image_url
                or not existing_book.description
                or existing_book.page_count is None
                or existing_book.page_count == 0
            )

            if needs_enrichment:
                logger.info(
                    f"Book {existing_book.title} has missing data, attempting enrichment..."
                )
                enriched = await self._enrich_existing_book(existing_book, cleaned_isbn)
                if enriched:
                    await self.db.commit()
                    await self.db.refresh(existing_book)
                    logger.info(f"Successfully enriched book: {existing_book.title}")

            return existing_book

        logger.info(f"Book not in DB, searching external APIs for ISBN: {cleaned_isbn}")
        metadata = await self._search_and_merge_apis(cleaned_isbn)

        if not metadata:
            logger.warning(f"No metadata found for ISBN: {cleaned_isbn}")
            return None

        mapping_result = ClassificationMappingService.map_book_classification_immediate(
            metadata
        )

        logger.info(
            f"Mapped book to {len(mapping_result['genres'])} genres "
            f"and {len(mapping_result['topics'])} topics"
        )

        cover_url = metadata.get("cover_image_url")
        local_cover_url = None

        if cover_url:
            cover_url_str = str(cover_url)
            logger.info(f"Attempting to download cover from: {cover_url_str}")
            try:
                file_service = FileUploadService()
                result = await file_service.download_and_save_book_cover(
                    cover_url_str, cleaned_isbn
                )
                if result:
                    _, local_cover_url = result
                    logger.info(
                        f"✅ Book cover downloaded and saved: {local_cover_url}"
                    )
                else:
                    logger.warning("⚠️  Failed to download cover, will use original URL")
            except Exception as e:
                logger.error(f"Error downloading book cover: {e}")

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
            genres=mapping_result["genres"],
            topics=mapping_result["topics"],
            cover_image_url=local_cover_url or cover_url,
            thumbnail_url=metadata.get("thumbnail_url"),
        )

        self.db.add(new_book)
        await self.db.commit()
        await self.db.refresh(new_book)

        logger.info(f"Created new book: {new_book.title} (ID: {new_book.id})")
        return new_book

    async def _search_and_merge_apis(self, isbn: str) -> dict[str, object] | None:
        google_data = await GoogleBooksClient.search_by_isbn(isbn)

        if not google_data:
            logger.info("Google Books failed, trying Open Library...")
            openlib_data = await OpenLibraryClient.search_by_isbn(isbn)
            return dict(openlib_data) if openlib_data else None

        needs_openlib = (
            not google_data.get("cover_image_url")
            or not google_data.get("description")
            or not google_data.get("page_count")
            or google_data.get("page_count") == 0
        )

        if needs_openlib:
            logger.info(
                "Google Books data incomplete, fetching from Open Library for merge..."
            )
            openlib_data = await OpenLibraryClient.search_by_isbn(isbn)

            if openlib_data:
                if not google_data.get("cover_image_url"):
                    google_data["cover_image_url"] = openlib_data.get("cover_image_url")

                if not google_data.get("description"):
                    google_data["description"] = openlib_data.get("description")

                if (
                    not google_data.get("page_count")
                    or google_data.get("page_count") == 0
                ):
                    google_data["page_count"] = openlib_data.get("page_count")

                if not google_data.get("publisher"):
                    google_data["publisher"] = openlib_data.get("publisher")

                logger.info("Successfully merged Google Books + Open Library data")

        return dict(google_data)

    async def _enrich_existing_book(self, book: Book, isbn: str) -> bool:
        metadata = await self._search_and_merge_apis(isbn)

        if not metadata:
            return False

        updated = False

        if not book.cover_image_url and metadata.get("cover_image_url"):
            cover_url = str(metadata["cover_image_url"])

            try:
                file_service = FileUploadService()
                result = await file_service.download_and_save_book_cover(
                    cover_url, isbn
                )
                if result:
                    _, local_cover_url = result
                    book.cover_image_url = local_cover_url
                    updated = True
                    logger.info(f"Added cover to existing book: {book.title}")
                else:
                    book.cover_image_url = cover_url
                    updated = True
            except Exception as e:
                logger.error(f"Failed to download cover for existing book: {e}")
                book.cover_image_url = cover_url
                updated = True

        if not book.description and metadata.get("description"):
            book.description = str(metadata["description"])
            updated = True
            logger.info(f"Added description to existing book: {book.title}")

        if (not book.page_count or book.page_count == 0) and metadata.get("page_count"):
            page_count_val = metadata["page_count"]
            try:
                book.page_count = int(str(page_count_val)) if page_count_val else None
            except (ValueError, TypeError):
                book.page_count = None
            updated = True
            logger.info(f"Added page_count to existing book: {book.title}")

        if not book.publisher and metadata.get("publisher"):
            book.publisher = str(metadata["publisher"])
            updated = True

        if not book.thumbnail_url and metadata.get("thumbnail_url"):
            book.thumbnail_url = str(metadata["thumbnail_url"])
            updated = True

        if not book.genres or not book.topics:
            try:
                mapping_result = (
                    ClassificationMappingService.map_book_classification_immediate(
                        metadata
                    )
                )

                if not book.genres and mapping_result["genres"]:
                    book.genres = mapping_result["genres"]
                    updated = True
                    logger.info(
                        f"Added genres to existing book {book.title}: "
                        f"{', '.join(book.genres)}"
                    )

                if not book.topics and mapping_result["topics"]:
                    book.topics = mapping_result["topics"]
                    updated = True
                    logger.info(
                        f"Added topics to existing book {book.title}: "
                        f"{', '.join(book.topics)}"
                    )

            except Exception as e:
                logger.error(f"Failed to map genres/topics for existing book: {e}")

        return updated

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
        exact_address = user.exact_address

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
            exact_address = geocode_result["formatted_address"]
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
            exact_address=exact_address,
            is_available=True,
        )

        self.db.add(new_offer)
        await self.db.commit()
        await self.db.refresh(new_offer, ["book", "owner"])

        all_comments = await self._get_all_user_comments(book.id)

        logger.info(f"Created book offer ID {new_offer.id} for user {user_id}")
        return BookOfferRead.from_db(new_offer, all_user_comments=all_comments)

    async def get_my_offers(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> tuple[list[BookOfferRead], int]:
        base_query = (
            select(BookOffer)
            .options(selectinload(BookOffer.book), selectinload(BookOffer.owner))
            .where(BookOffer.owner_id == user_id)
        )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = await self.db.scalar(count_query) or 0

        query = (
            base_query.order_by(BookOffer.created_at.desc()).offset(skip).limit(limit)
        )

        result = await self.db.execute(query)
        offers = result.scalars().all()

        offer_reads = []
        for offer in offers:
            all_comments = await self._get_all_user_comments(offer.book_id)
            offer_reads.append(
                BookOfferRead.from_db(offer, all_user_comments=all_comments)
            )

        return offer_reads, total

    async def update_offer(
        self, offer_id: int, user_id: int, data: BookOfferUpdate
    ) -> BookOfferRead:
        query = (
            select(BookOffer)
            .options(selectinload(BookOffer.book), selectinload(BookOffer.owner))
            .where(BookOffer.id == offer_id)
        )
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
            offer.exact_address = geocode_result["formatted_address"]
            update_data.pop("custom_location")

        for key, value in update_data.items():
            if hasattr(offer, key):
                setattr(offer, key, value)

        await self.db.commit()
        await self.db.refresh(
            offer,
            [
                "id",
                "book_id",
                "owner_id",
                "condition",
                "notes",
                "user_comment",
                "location_lat",
                "location_lon",
                "location_district",
                "is_available",
                "created_at",
                "updated_at",
                "reserved_until",
                "reserved_by_user_id",
                "custom_cover_image_url",
                "book",
                "owner",
            ],
        )

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
