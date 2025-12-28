import logging
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram import TelegramNotifier
from app.models.book import Book
from app.models.book_enrichment_bookmark import BookLastChecked
from app.services.classification_mapping_service import ClassificationMappingService
from app.services.google_books_client import BookMetadata, GoogleBooksClient
from app.services.open_library_client import OpenLibraryClient

logger = logging.getLogger(__name__)


class EnrichmentStats(TypedDict):
    books_checked: int
    books_updated: int
    books_skipped_recently_checked: int
    google_requests: int
    openlibrary_requests: int
    genres_mapped: int
    topics_mapped: int
    last_processed_id: int | None


class BookMetadataEnrichmentService:
    MAX_REQUESTS_PER_API: int = 50
    RECHECK_INTERVAL_DAYS: int = 30

    @classmethod
    async def enrich_books(
        cls, db: AsyncSession, last_processed_id: int | None = None
    ) -> EnrichmentStats:
        stats: EnrichmentStats = {
            "books_checked": 0,
            "books_updated": 0,
            "books_skipped_recently_checked": 0,
            "google_requests": 0,
            "openlibrary_requests": 0,
            "genres_mapped": 0,
            "topics_mapped": 0,
            "last_processed_id": last_processed_id,
        }

        books_to_process = await cls._get_incomplete_books(
            db, last_processed_id, limit=cls.MAX_REQUESTS_PER_API
        )

        if not books_to_process:
            if last_processed_id is not None and last_processed_id > 0:
                logger.info(
                    "No incomplete books found after ID "
                    f"{last_processed_id}, restarting from beginning"
                )
                stats["last_processed_id"] = None
                return stats
            else:
                logger.info("No incomplete books found for enrichment")
                return stats

        logger.info(
            f"Found {len(books_to_process)} incomplete books starting from "
            f"ID {books_to_process[0].id if books_to_process else 'N/A'}"
        )

        for book in books_to_process:
            stats["last_processed_id"] = book.id

            if await cls._was_recently_checked(db, book.id):
                stats["books_skipped_recently_checked"] += 1
                logger.debug(
                    f"Skipping book '{book.title}' (ID: {book.id}) - "
                    f"checked within last {cls.RECHECK_INTERVAL_DAYS} days"
                )
                continue

            stats["books_checked"] += 1

            missing_fields = cls._get_missing_fields(book)
            if not missing_fields:
                await cls._update_last_checked(db, book.id)
                continue

            updated = False
            updated_fields: list[str] = []

            google_metadata = None
            ol_metadata = None

            if stats["google_requests"] < cls.MAX_REQUESTS_PER_API:
                updated, fields, google_metadata = await cls._try_enrich_from_google(
                    db, book, missing_fields
                )
                stats["google_requests"] += 1

                if updated:
                    updated_fields.extend(fields)
                    missing_fields = [f for f in missing_fields if f not in fields]

            if (
                missing_fields
                and stats["openlibrary_requests"] < cls.MAX_REQUESTS_PER_API
            ):
                (
                    ol_updated,
                    ol_fields,
                    ol_metadata,
                ) = await cls._try_enrich_from_openlibrary(db, book, missing_fields)
                stats["openlibrary_requests"] += 1

                if ol_updated:
                    updated_fields.extend(ol_fields)
                    updated = True

            await cls._update_last_checked(db, book.id)

            if "genres" in missing_fields or "topics" in missing_fields:
                raw_categories = []
                raw_subjects = []

                if google_metadata:
                    raw_categories.extend(google_metadata.get("categories", []))

                if ol_metadata:
                    raw_subjects.extend(ol_metadata.get("subjects", []))

                if raw_categories or raw_subjects:
                    try:
                        mapping_result = (
                            ClassificationMappingService.map_book_classification(
                                raw_categories=raw_categories,
                                raw_subjects=raw_subjects,
                            )
                        )

                        if "genres" in missing_fields and mapping_result["genres"]:
                            book.genres = mapping_result["genres"]
                            updated_fields.append("genres")
                            stats["genres_mapped"] += 1
                            updated = True

                        if "topics" in missing_fields and mapping_result["topics"]:
                            book.topics = mapping_result["topics"]
                            updated_fields.append("topics")
                            stats["topics_mapped"] += 1
                            updated = True

                    except Exception as e:
                        logger.error(
                            f"Classification mapping error for book {book.id}: {e}"
                        )

            if updated and updated_fields:
                await db.commit()
                stats["books_updated"] += 1

                await cls._send_telegram_notification(book.title, updated_fields)

                logger.info(
                    f"Updated book '{book.title}' (ID: {book.id}): "
                    f"{', '.join(updated_fields)}"
                )

            if (
                stats["google_requests"] >= cls.MAX_REQUESTS_PER_API
                and stats["openlibrary_requests"] >= cls.MAX_REQUESTS_PER_API
            ):
                logger.info("Reached max requests for both APIs")
                break

        logger.info(
            f"Enrichment completed: {stats['books_updated']}/{stats['books_checked']} "
            f"books updated, {stats['books_skipped_recently_checked']} skipped (recently checked), "
            f"Google: {stats['google_requests']}, OpenLibrary: {stats['openlibrary_requests']}"
        )

        return stats

    @classmethod
    async def _get_incomplete_books(
        cls, db: AsyncSession, last_processed_id: int | None, limit: int
    ) -> list[Book]:
        query = (
            select(Book)
            .where(Book.id > (last_processed_id or 0))
            .order_by(Book.id)
            .limit(limit * 2)
        )

        result = await db.execute(query)
        all_books = result.scalars().all()

        incomplete_books = [book for book in all_books if cls._get_missing_fields(book)]

        return incomplete_books[:limit]

    @classmethod
    async def _was_recently_checked(cls, db: AsyncSession, book_id: int) -> bool:
        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=cls.RECHECK_INTERVAL_DAYS
        )

        query = select(BookLastChecked).where(
            BookLastChecked.book_id == book_id,
            BookLastChecked.last_checked_at > cutoff_date,
        )

        result = await db.execute(query)
        last_checked = result.scalar_one_or_none()

        return last_checked is not None

    @classmethod
    async def _update_last_checked(cls, db: AsyncSession, book_id: int) -> None:
        query = select(BookLastChecked).where(BookLastChecked.book_id == book_id)
        result = await db.execute(query)
        record = result.scalar_one_or_none()

        if record:
            record.last_checked_at = datetime.now(timezone.utc)
        else:
            new_record = BookLastChecked(
                book_id=book_id, last_checked_at=datetime.now(timezone.utc)
            )
            db.add(new_record)

        await db.commit()

    @classmethod
    def _get_missing_fields(cls, book: Book) -> list[str]:
        missing: list[str] = []

        if not book.title:
            missing.append("title")
        if not book.description:
            missing.append("description")
        if not book.cover_image_url:
            missing.append("cover_image_url")
        if not book.thumbnail_url:
            missing.append("thumbnail_url")
        if not book.authors or len(book.authors) == 0:
            missing.append("authors")
        if not book.publisher:
            missing.append("publisher")
        if not book.published_date:
            missing.append("published_date")
        if not book.language:
            missing.append("language")
        if not book.page_count:
            missing.append("page_count")
        if not book.genres or len(book.genres) == 0:
            missing.append("genres")
        if not book.topics or len(book.topics) == 0:
            missing.append("topics")

        return missing

    @classmethod
    async def _try_enrich_from_google(
        cls, db: AsyncSession, book: Book, missing_fields: list[str]
    ) -> tuple[bool, list[str], BookMetadata | None]:
        try:
            metadata = await GoogleBooksClient.search_by_isbn(book.isbn_13)

            if not metadata:
                return False, [], None

            updated, fields = cls._apply_metadata(book, metadata, missing_fields)
            return updated, fields, metadata

        except Exception as e:
            logger.error(f"Google Books API error for book {book.id}: {e}")
            return False, [], None

    @classmethod
    async def _try_enrich_from_openlibrary(
        cls, db: AsyncSession, book: Book, missing_fields: list[str]
    ) -> tuple[bool, list[str], BookMetadata | None]:
        try:
            metadata = await OpenLibraryClient.search_by_isbn(book.isbn_13)

            if not metadata:
                return False, [], None

            updated, fields = cls._apply_metadata(book, metadata, missing_fields)
            return updated, fields, metadata

        except Exception as e:
            logger.error(f"Open Library API error for book {book.id}: {e}")
            return False, [], None

    @classmethod
    def _apply_metadata(
        cls, book: Book, metadata: BookMetadata, missing_fields: list[str]
    ) -> tuple[bool, list[str]]:
        updated_fields: list[str] = []

        title = metadata.get("title")
        if "title" in missing_fields and title:
            book.title = title
            updated_fields.append("title")

        description = metadata.get("description")
        if "description" in missing_fields and description:
            book.description = description
            updated_fields.append("description")

        cover_image_url = metadata.get("cover_image_url")
        if "cover_image_url" in missing_fields and cover_image_url:
            book.cover_image_url = cover_image_url
            updated_fields.append("cover_image_url")

        thumbnail_url = metadata.get("thumbnail_url")
        if "thumbnail_url" in missing_fields and thumbnail_url:
            book.thumbnail_url = thumbnail_url
            updated_fields.append("thumbnail_url")

        authors = metadata.get("authors")
        if "authors" in missing_fields and authors and len(authors) > 0:
            book.authors = authors
            updated_fields.append("authors")

        publisher = metadata.get("publisher")
        if "publisher" in missing_fields and publisher:
            book.publisher = publisher
            updated_fields.append("publisher")

        published_date = metadata.get("published_date")
        if "published_date" in missing_fields and published_date:
            book.published_date = published_date
            updated_fields.append("published_date")

        language = metadata.get("language")
        if "language" in missing_fields and language:
            book.language = language
            updated_fields.append("language")

        page_count = metadata.get("page_count")
        if "page_count" in missing_fields and page_count:
            book.page_count = page_count
            updated_fields.append("page_count")

        return len(updated_fields) > 0, updated_fields

    @classmethod
    async def _send_telegram_notification(
        cls, book_title: str, updated_fields: list[str]
    ) -> None:
        fields_str = ", ".join(updated_fields)
        message = (
            f"📚 <b>Buch-Update</b>\n\n"
            f"<b>Titel:</b> {book_title}\n"
            f"<b>Erweiterte Felder:</b> {fields_str}"
        )

        await TelegramNotifier.send_message(message, level="info")
