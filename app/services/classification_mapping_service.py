import logging
from typing import Sequence

logger = logging.getLogger(__name__)


class ClassificationMappingService:
    @classmethod
    def map_book_classification(
        cls,
        ddc_classes: list[str],
        raw_categories: list[str],
        raw_subjects: list[str],
        wikidata_topics: Sequence[dict[str, str | None]],
    ) -> dict[str, list[str]]:
        from app.constants.book_classification import (
            CATEGORY_TO_GENRE,
            CATEGORY_TO_TOPIC,
            DDC_TO_GENRE,
        )

        genre_slugs = set()
        topic_slugs = set()

        if ddc_classes:
            for ddc_code in ddc_classes:
                genre_slug = cls._map_ddc_to_genre(ddc_code, DDC_TO_GENRE)
                if genre_slug:
                    genre_slugs.add(genre_slug)

        if raw_categories:
            for category in raw_categories:
                genre_slug = cls._map_category_to_genre(category, CATEGORY_TO_GENRE)
                if genre_slug:
                    genre_slugs.add(genre_slug)

                topic_slug = cls._map_category_to_topic(category, CATEGORY_TO_TOPIC)
                if topic_slug:
                    topic_slugs.add(topic_slug)

        if raw_subjects:
            for subject in raw_subjects:
                topic_slug = cls._map_category_to_topic(subject, CATEGORY_TO_TOPIC)
                if topic_slug:
                    topic_slugs.add(topic_slug)

        if wikidata_topics:
            for wd_topic in wikidata_topics:
                label_de = wd_topic.get("label_de")
                label_en = wd_topic.get("label_en")

                if label_de:
                    mapped = cls._map_category_to_topic(label_de, CATEGORY_TO_TOPIC)
                    if mapped:
                        topic_slugs.add(mapped)

                if label_en:
                    mapped = cls._map_category_to_topic(label_en, CATEGORY_TO_TOPIC)
                    if mapped:
                        topic_slugs.add(mapped)

        if not genre_slugs:
            genre_slugs.add("non_fiction")

        result = {
            "genres": sorted(list(genre_slugs)),
            "topics": sorted(list(topic_slugs)),
        }

        logger.debug(
            f"Mapped {len(raw_categories)} categories + {len(raw_subjects)} subjects "
            f"to {len(result['genres'])} genres and {len(result['topics'])} topics"
        )

        return result

    @classmethod
    def map_book_classification_immediate(
        cls,
        metadata: dict[str, object],
    ) -> dict[str, list[str]]:
        ddc_classes = metadata.get("ddc_classes", [])
        if isinstance(ddc_classes, list):
            ddc_classes = [str(x) for x in ddc_classes]
        else:
            ddc_classes = []

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
            ddc_classes=ddc_classes,
            raw_categories=raw_categories,
            raw_subjects=raw_subjects,
            wikidata_topics=[],
        )

    @classmethod
    def _map_ddc_to_genre(
        cls, ddc_code: str, ddc_to_genre_map: dict[str, str]
    ) -> str | None:
        ddc_num = ddc_code.split()[0] if " " in ddc_code else ddc_code

        try:
            ddc_float = float(ddc_num)
            ddc_int = int(ddc_float)

            ddc_str = str(ddc_int)

            if ddc_str in ddc_to_genre_map:
                return ddc_to_genre_map[ddc_str]

            if ddc_int >= 0 and ddc_int < 100:
                return ddc_to_genre_map.get("000", "technology")
            elif ddc_int >= 100 and ddc_int < 200:
                if ddc_int >= 150 and ddc_int < 160:
                    return "non_fiction"
                return ddc_to_genre_map.get("100", "philosophy")
            elif ddc_int >= 200 and ddc_int < 300:
                return ddc_to_genre_map.get("200", "religion")
            elif ddc_int >= 300 and ddc_int < 400:
                if ddc_int >= 330 and ddc_int < 340:
                    return "business"
                return "non_fiction"
            elif ddc_int >= 500 and ddc_int < 600:
                return "science"
            elif ddc_int >= 600 and ddc_int < 700:
                if ddc_int >= 640 and ddc_int < 650:
                    return "cooking"
                if ddc_int >= 610 and ddc_int < 620:
                    return "science"
                return "technology"
            elif ddc_int >= 700 and ddc_int < 800:
                if ddc_int >= 790 and ddc_int < 800:
                    return "sports"
                return "arts"
            elif ddc_int >= 800 and ddc_int < 900:
                return "fiction"
            elif ddc_int >= 900 and ddc_int < 1000:
                if ddc_int >= 910 and ddc_int < 920:
                    return "travel"
                if ddc_int >= 920 and ddc_int < 930:
                    return "biography"
                return "history"

        except (ValueError, AttributeError):
            pass

        return None

    @classmethod
    def _map_category_to_genre(
        cls, category: str, category_to_genre_map: dict[str, str]
    ) -> str | None:
        category_lower = category.lower().strip()

        if category_lower in category_to_genre_map:
            return category_to_genre_map[category_lower]

        for pattern, genre in category_to_genre_map.items():
            if pattern in category_lower:
                return genre

        return None

    @classmethod
    def _map_category_to_topic(
        cls, category: str, category_to_topic_map: dict[str, str]
    ) -> str | None:
        category_lower = category.lower().strip()

        if category_lower in category_to_topic_map:
            return category_to_topic_map[category_lower]

        for pattern, topic in category_to_topic_map.items():
            if pattern in category_lower:
                return topic

        return None
