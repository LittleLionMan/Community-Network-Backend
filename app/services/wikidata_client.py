import logging

import httpx

logger = logging.getLogger(__name__)


class WikidataClient:
    SPARQL_ENDPOINT: str = "https://query.wikidata.org/sparql"
    TIMEOUT: float = 15.0
    USER_AGENT: str = "BookExchangeApp/1.0"

    @classmethod
    async def search_topics_by_isbn(cls, isbn: str) -> list[dict[str, str | None]]:
        if not isbn:
            return []

        cleaned_isbn = isbn.replace("-", "").replace(" ", "").strip()

        query = f"""
        SELECT ?topic ?topicLabelDe ?topicLabelEn WHERE {{
          ?work wdt:P212 "{cleaned_isbn}" .
          OPTIONAL {{ ?work wdt:P921 ?topic . }}
          OPTIONAL {{
            ?topic rdfs:label ?topicLabelDe .
            FILTER(LANG(?topicLabelDe) = "de")
          }}
          OPTIONAL {{
            ?topic rdfs:label ?topicLabelEn .
            FILTER(LANG(?topicLabelEn) = "en")
          }}
        }}
        LIMIT 20
        """

        try:
            async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
                response = await client.get(
                    cls.SPARQL_ENDPOINT,
                    params={"query": query, "format": "json"},
                    headers={"User-Agent": cls.USER_AGENT},
                )

                if response.status_code != 200:
                    logger.warning(
                        f"Wikidata SPARQL returned status {response.status_code}"
                    )
                    return []

                data = response.json()
                bindings = data.get("results", {}).get("bindings", [])

                if not bindings:
                    logger.info(f"No Wikidata topics found for ISBN {cleaned_isbn}")
                    return []

                topics_dict: dict[str, dict[str, str | None]] = {}

                for binding in bindings:
                    if "topic" not in binding:
                        continue

                    topic_uri = binding["topic"]["value"]
                    topic_id = topic_uri.split("/")[-1]

                    if topic_id not in topics_dict:
                        topics_dict[topic_id] = {
                            "topic_id": topic_id,
                            "label_de": None,
                            "label_en": None,
                        }

                    if "topicLabelDe" in binding:
                        topics_dict[topic_id]["label_de"] = binding["topicLabelDe"][
                            "value"
                        ]

                    if "topicLabelEn" in binding:
                        topics_dict[topic_id]["label_en"] = binding["topicLabelEn"][
                            "value"
                        ]

                logger.info(
                    f"Found {len(topics_dict)} topics via Wikidata for ISBN {cleaned_isbn}"
                )
                return list(topics_dict.values())

        except httpx.TimeoutException:
            logger.error(f"Wikidata timeout for ISBN: {cleaned_isbn}")
            return []
        except Exception as e:
            logger.error(f"Wikidata error for ISBN {cleaned_isbn}: {e}")
            return []
