import logging
from typing import Any, TypedDict, cast

import httpx

logger = logging.getLogger(__name__)


class BookMetadata(TypedDict, total=False):
    isbn_13: str
    isbn_10: str | None
    title: str
    authors: list[str]
    publisher: str | None
    published_date: str | None
    description: str | None
    language: str
    page_count: int | None
    categories: list[str]
    cover_image_url: str | None
    thumbnail_url: str | None


class GoogleBooksClient:
    BASE_URL: str = "https://www.googleapis.com/books/v1/volumes"
    TIMEOUT: float = 10.0

    @classmethod
    async def search_by_isbn(cls, isbn: str) -> BookMetadata | None:
        if not isbn:
            return None

        cleaned_isbn = isbn.replace("-", "").replace(" ", "").strip()

        try:
            async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
                response = await client.get(
                    cls.BASE_URL, params={"q": f"isbn:{cleaned_isbn}"}
                )

                if response.status_code != 200:
                    logger.warning(
                        f"Google Books API returned status {response.status_code}"
                    )
                    return None

                data: dict[str, Any] = cast(dict[str, Any], response.json())

                if not data.get("items"):
                    logger.info(
                        f"No results from Google Books for ISBN: {cleaned_isbn}"
                    )
                    return None

                items = cast(list[dict[str, Any]], data.get("items", []))
                volume = items[0]
                volume_info: dict[str, Any] = cast(
                    dict[str, Any], volume.get("volumeInfo", {})
                )

                identifiers = cast(
                    list[dict[str, Any]], volume_info.get("industryIdentifiers", [])
                )
                isbn_13 = None
                isbn_10 = None

                for identifier in identifiers:
                    id_type = str(identifier.get("type", ""))
                    if id_type == "ISBN_13":
                        isbn_13 = str(identifier.get("identifier", ""))
                    elif id_type == "ISBN_10":
                        isbn_10 = str(identifier.get("identifier", ""))

                if not isbn_13 and len(cleaned_isbn) == 13:
                    isbn_13 = cleaned_isbn
                elif not isbn_10 and len(cleaned_isbn) == 10:
                    isbn_10 = cleaned_isbn

                if not isbn_13 and isbn_10:
                    isbn_13 = cls._convert_isbn10_to_isbn13(isbn_10)

                if not isbn_13:
                    logger.warning(f"Could not determine ISBN-13 for: {cleaned_isbn}")
                    return None

                image_links: dict[str, Any] = cast(
                    dict[str, Any], volume_info.get("imageLinks", {})
                )

                cover_image_url = None
                if "large" in image_links:
                    cover_image_url = str(image_links["large"])
                elif "medium" in image_links:
                    cover_image_url = str(image_links["medium"])
                elif "thumbnail" in image_links:
                    cover_image_url = str(image_links["thumbnail"])
                elif "smallThumbnail" in image_links:
                    cover_image_url = str(image_links["smallThumbnail"])

                thumbnail_url = None
                if "thumbnail" in image_links:
                    thumbnail_url = str(image_links["thumbnail"])
                elif "smallThumbnail" in image_links:
                    thumbnail_url = str(image_links["smallThumbnail"])

                metadata: BookMetadata = {
                    "isbn_13": isbn_13,
                    "isbn_10": isbn_10,
                    "title": str(volume_info.get("title", "Unbekannter Titel")),
                    "authors": cast(list[str], volume_info.get("authors", [])),
                    "publisher": str(volume_info["publisher"])
                    if "publisher" in volume_info
                    else None,
                    "published_date": str(volume_info["publishedDate"])
                    if "publishedDate" in volume_info
                    else None,
                    "description": str(volume_info["description"])
                    if "description" in volume_info
                    else None,
                    "language": str(volume_info.get("language", "de")),
                    "page_count": int(volume_info["pageCount"])
                    if "pageCount" in volume_info
                    else None,
                    "categories": cast(list[str], volume_info.get("categories", [])),
                    "cover_image_url": cover_image_url,
                    "thumbnail_url": thumbnail_url,
                }

                logger.info(f"Found book via Google Books: {metadata['title']}")
                return metadata

        except httpx.TimeoutException:
            logger.error(f"Google Books API timeout for ISBN: {cleaned_isbn}")
            return None
        except Exception as e:
            logger.error(f"Google Books API error: {e}")
            return None

    @staticmethod
    def _convert_isbn10_to_isbn13(isbn10: str) -> str:
        if len(isbn10) != 10:
            return isbn10

        isbn13_base = "978" + isbn10[:-1]

        checksum = 0
        for i, digit in enumerate(isbn13_base):
            weight = 1 if i % 2 == 0 else 3
            checksum += int(digit) * weight

        check_digit = (10 - (checksum % 10)) % 10

        return isbn13_base + str(check_digit)
