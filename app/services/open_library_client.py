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


class OpenLibraryClient:
    BASE_URL: str = "https://openlibrary.org"
    TIMEOUT: float = 15.0

    @classmethod
    async def search_by_isbn(cls, isbn: str) -> BookMetadata | None:
        if not isbn:
            return None

        cleaned_isbn = isbn.replace("-", "").replace(" ", "").strip()

        try:
            async with httpx.AsyncClient(
                timeout=cls.TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(f"{cls.BASE_URL}/isbn/{cleaned_isbn}.json")

                if response.status_code == 404:
                    logger.info(
                        f"No results from Open Library for ISBN: {cleaned_isbn}"
                    )
                    return None

                if response.status_code != 200:
                    logger.warning(
                        f"Open Library API returned status {response.status_code}"
                    )
                    return None

                data: dict[str, Any] = cast(dict[str, Any], response.json())

                isbn_13 = None
                isbn_10 = None

                isbn_13_list = cast(list[str], data.get("isbn_13", []))
                for isbn_entry in isbn_13_list:
                    isbn_13 = isbn_entry
                    break

                isbn_10_list = cast(list[str], data.get("isbn_10", []))
                for isbn_entry in isbn_10_list:
                    isbn_10 = isbn_entry
                    break

                if not isbn_13 and len(cleaned_isbn) == 13:
                    isbn_13 = cleaned_isbn
                elif not isbn_10 and len(cleaned_isbn) == 10:
                    isbn_10 = cleaned_isbn

                if not isbn_13:
                    logger.warning(
                        f"Could not determine ISBN-13 from Open Library: {cleaned_isbn}"
                    )
                    return None

                authors = []
                author_refs = cast(list[dict[str, Any]], data.get("authors", []))
                for author_ref in author_refs:
                    if isinstance(author_ref, dict) and "key" in author_ref:
                        author_data = await cls._fetch_author(
                            str(author_ref["key"]), client
                        )
                        if author_data:
                            authors.append(author_data)

                covers = cast(list[int], data.get("covers", []))
                cover_id = covers[0] if covers else None
                cover_url = None
                thumbnail_url = None

                if cover_id:
                    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                    thumbnail_url = (
                        f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                    )

                description_value = data.get("description")
                description: str | None = None
                if isinstance(description_value, dict):
                    value = description_value.get("value")
                    description = str(value) if value else None
                elif isinstance(description_value, str):
                    description = description_value

                publishers = cast(list[str], data.get("publishers", []))
                publisher = publishers[0] if publishers else None

                publish_date = (
                    str(data.get("publish_date", ""))
                    if data.get("publish_date")
                    else None
                )

                metadata: BookMetadata = {
                    "isbn_13": isbn_13,
                    "isbn_10": isbn_10,
                    "title": str(data.get("title", "Unbekannter Titel")),
                    "authors": authors,
                    "publisher": publisher,
                    "published_date": publish_date,
                    "description": description,
                    "language": cls._extract_language(
                        cast(list[Any], data.get("languages", []))
                    ),
                    "page_count": int(data["number_of_pages"])
                    if "number_of_pages" in data
                    else None,
                    "categories": cast(list[str], data.get("subjects", []))[:10],
                    "cover_image_url": cover_url,
                    "thumbnail_url": thumbnail_url,
                }

                logger.info(f"Found book via Open Library: {metadata['title']}")
                return metadata

        except httpx.TimeoutException:
            logger.error(f"Open Library API timeout for ISBN: {cleaned_isbn}")
            return None
        except Exception as e:
            logger.error(f"Open Library API error: {e}")
            return None

    @classmethod
    async def _fetch_author(
        cls, author_key: str, client: httpx.AsyncClient
    ) -> str | None:
        try:
            response = await client.get(f"{cls.BASE_URL}{author_key}.json")
            if response.status_code == 200:
                author_data: dict[str, Any] = cast(dict[str, Any], response.json())
                return str(author_data.get("name", "Unbekannt"))
        except Exception as e:
            logger.warning(f"Failed to fetch author {author_key}: {e}")
        return None

    @staticmethod
    def _extract_language(languages: list[Any]) -> str:
        if not languages:
            return "de"

        first_lang = languages[0]
        if isinstance(first_lang, dict):
            lang_key = str(first_lang.get("key", ""))
            if "/languages/" in lang_key:
                return lang_key.split("/")[-1]
        elif isinstance(first_lang, str):
            return first_lang

        return "de"
