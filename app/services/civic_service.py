from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.event import EventCategory

class CivicService:
    db: AsyncSession
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_political_category_ids(self) -> list[int]:
        try:
            result = await self.db.execute(
                select(EventCategory.id).where(
                    EventCategory.name.ilike('%politik%')
                )
            )

            category_ids = list(result.scalars().all())
            print(f"DEBUG CivicService: Found IDs = {category_ids}")
            return category_ids

        except Exception as e:
            print(f"DEBUG CivicService: Error = {e}")
            return []

    async def get_politics_category_id(self) -> int | None:
        try:
            result = await self.db.execute(
                select(EventCategory.id).where(
                    EventCategory.name.ilike('%politik%')
                ).limit(1)
            )

            row = result.first()
            category_id = row[0] if row else None
            return category_id

        except Exception:
            return None

    async def is_political_category(self, category_id: int) -> bool:
        political_ids = await self.get_political_category_ids()
        return category_id in political_ids
