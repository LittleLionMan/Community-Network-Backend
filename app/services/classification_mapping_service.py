import logging

logger = logging.getLogger(__name__)


class ClassificationMappingService:
    @classmethod
    def map_book_classification(
        cls,
        raw_categories: list[str],
        raw_subjects: list[str],
    ) -> dict[str, list[str]]:
        from app.constants.book_classification import (
            CATEGORY_TO_GENRE,
            CATEGORY_TO_TOPIC,
        )

        genre_slugs = set()
        topic_slugs = set()

        for category in raw_categories:
            genre_slug = cls._map_category_to_genre(category, CATEGORY_TO_GENRE)
            if genre_slug:
                genre_slugs.add(genre_slug)

            topic_slug = cls._map_category_to_topic(category, CATEGORY_TO_TOPIC)
            if topic_slug:
                topic_slugs.add(topic_slug)

        for subject in raw_subjects:
            topic_slug = cls._map_category_to_topic(subject, CATEGORY_TO_TOPIC)
            if topic_slug:
                topic_slugs.add(topic_slug)

        return {
            "genres": sorted(list(genre_slugs)),
            "topics": sorted(list(topic_slugs)),
        }

    @classmethod
    def map_book_classification_immediate(
        cls,
        metadata: dict[str, object],
    ) -> dict[str, list[str]]:
        raw_categories = metadata.get("categories", [])
        if isinstance(raw_categories, list):
            raw_categories = [str(x) for x in raw_categories]
        else:
            raw_categories = []

        raw_subjects = metadata.get("subjects", [])
        if isinstance(raw_subjects, list):
            raw_subjects = [str(x) for x in raw_subjects]
        else:
            raw_subjects = []

        return cls.map_book_classification(
            raw_categories=raw_categories,
            raw_subjects=raw_subjects,
        )

    @classmethod
    def _map_category_to_genre(
        cls, category: str, category_to_genre_map: dict[str, str]
    ) -> str | None:
        category_lower = category.lower().strip()

        if category_lower in category_to_genre_map:
            return category_to_genre_map[category_lower]

        sorted_patterns = sorted(category_to_genre_map.keys(), key=len, reverse=True)

        for pattern in sorted_patterns:
            if (
                f" {pattern} " in f" {category_lower} "
                or category_lower.startswith(f"{pattern} ")
                or category_lower.endswith(f" {pattern}")
            ):
                return category_to_genre_map[pattern]

        return None

    @classmethod
    def _map_category_to_topic(
        cls, category: str, category_to_topic_map: dict[str, str]
    ) -> str | None:
        category_lower = category.lower().strip()

        if category_lower in category_to_topic_map:
            return category_to_topic_map[category_lower]

        sorted_patterns = sorted(category_to_topic_map.keys(), key=len, reverse=True)

        for pattern in sorted_patterns:
            if (
                f" {pattern} " in f" {category_lower} "
                or category_lower.startswith(f"{pattern} ")
                or category_lower.endswith(f" {pattern}")
            ):
                return category_to_topic_map[pattern]

        return None
