from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
import re

from sqlalchemy.sql import ColumnElement
from ..models.service import Service


class ServiceMatchingService:
    db: AsyncSession
    keyword_pattern: re.Pattern[str]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.keyword_pattern = re.compile(r"^[a-zA-ZäöüÄÖÜß\s\-_0-9]{2,20}$")

    async def find_matching_services(
        self, user_id: int, limit: int = 10
    ) -> list[Service]:
        user_services = await self.db.execute(
            select(Service).where(Service.user_id == user_id, Service.is_active)
        )
        user_services_list = list(user_services.scalars().all())

        if not user_services_list:
            return await self._get_popular_services(limit)

        keywords = self._extract_safe_keywords(user_services_list)

        if not keywords:
            return await self._get_popular_services(limit)

        user_offering_types = {s.is_offering for s in user_services_list}
        target_offering = False if True in user_offering_types else True

        return await self._search_services_secure(
            keywords, target_offering, user_id, limit
        )

    def _extract_safe_keywords(self, services: list[Service]) -> list[str]:
        keywords: set[str] = set()

        for service in services:
            text = f"{service.title} {service.description}".lower()

            words: list[str] = re.findall(r"\b[a-zA-ZäöüÄÖÜß]{3,15}\b", text)

            for word in words:
                if self.keyword_pattern.match(word) and len(word) >= 3:
                    keywords.add(word.lower())

                if len(keywords) >= 10:
                    break

        return list(keywords)[:5]

    async def _search_services_secure(
        self,
        keywords: list[str],
        target_offering: bool,
        exclude_user_id: int,
        limit: int,
    ) -> list[Service]:
        try:
            search_conditions: list[ColumnElement[bool]] = []

            for i in enumerate(keywords[:5]):
                param_name = f"keyword_{i}"
                search_conditions.extend(
                    [
                        Service.title.ilike(f"%:{param_name}%"),
                        Service.description.ilike(f"%:{param_name}%"),
                    ]
                )

            if search_conditions:
                query = (
                    select(Service)
                    .where(
                        and_(
                            Service.is_offering == target_offering,
                            Service.user_id != exclude_user_id,
                            Service.is_active,
                            or_(*search_conditions),
                        )
                    )
                    .limit(limit)
                )

                params = {
                    f"keyword_{i}": keyword for i, keyword in enumerate(keywords[:5])
                }
                result = await self.db.execute(query, params)
                matches = list(result.scalars().all())

                if matches:
                    return matches

            return await self._get_recent_services_by_type(
                target_offering, exclude_user_id, limit
            )

        except Exception as e:
            print(f"Search error: {e}")
            return await self._get_popular_services(limit)

    async def _get_recent_services_by_type(
        self, is_offering: bool, exclude_user_id: int, limit: int
    ) -> list[Service]:
        result = await self.db.execute(
            select(Service)
            .where(
                and_(
                    Service.is_offering == is_offering,
                    Service.user_id != exclude_user_id,
                    Service.is_active,
                )
            )
            .order_by(Service.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _get_popular_services(self, limit: int) -> list[Service]:
        result = await self.db.execute(
            select(Service)
            .where(Service.is_active)
            .order_by(Service.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_service_request(
        self, user_id: int, service_id: int, message: str | None = None
    ) -> bool:
        if message:
            message = message.strip()[:500]

        service = await self.db.get(Service, service_id)
        if not service or service.user_id == user_id:
            return False

        # TODO: Implement proper service interest tracking
        print(f"User {user_id} interested in service {service_id}: {message}")
        return True
