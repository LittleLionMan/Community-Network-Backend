from typing import List, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from ..models.service import Service
from ..models.user import User

class ServiceMatchingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_matching_services(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[Service]:
        user_services = await self.db.execute(
            select(Service).where(
                Service.user_id == user_id,
                Service.is_active == True
            )
        )
        user_services_list = list(user_services.scalars().all())

        if not user_services_list:
            return await self._get_popular_services(limit)

        keywords = set()
        for service in user_services_list:
            words = (service.title + " " + service.description).lower().split()
            keywords.update([w for w in words if len(w) > 3])

        if not keywords:
            return await self._get_popular_services(limit)

        user_offering_types = {s.is_offering for s in user_services_list}
        target_offering = False if True in user_offering_types else True

        conditions = []
        for keyword in list(keywords)[:5]:
            conditions.extend([
                Service.title.ilike(f"%{keyword}%"),
                Service.description.ilike(f"%{keyword}%")
            ])

        if conditions:
            result = await self.db.execute(
                select(Service).where(
                    and_(
                        Service.is_offering == target_offering,
                        Service.user_id != user_id,
                        Service.is_active == True,
                        or_(*conditions)
                    )
                ).limit(limit)
            )
            matches = list(result.scalars().all())

            if matches:
                return matches

        result = await self.db.execute(
            select(Service).where(
                and_(
                    Service.is_offering == target_offering,
                    Service.user_id != user_id,
                    Service.is_active == True
                )
            ).order_by(Service.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def _get_popular_services(self, limit: int) -> List[Service]:
        """Get recently created services (proxy for popular)"""
        result = await self.db.execute(
            select(Service).where(
                Service.is_active == True
            ).order_by(Service.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def create_service_request(
        self,
        user_id: int,
        service_id: int,
        message: Optional[str] = None
    ) -> bool:
        service = await self.db.get(Service, service_id)
        if not service or service.user_id == user_id:
            return False

        # TODO: Implement contact/messaging system
        # For now, we could store in a simple ServiceInterest table
        print(f"User {user_id} interested in service {service_id}: {message}")

        return True
