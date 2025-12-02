from datetime import date, datetime, time

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_availability import UserAvailability


class AvailabilityService:
    @staticmethod
    async def create_slot(
        db: AsyncSession,
        user_id: int,
        slot_data: dict[str, str | int | date | time | datetime | bool | None],
    ) -> UserAvailability:
        slot = UserAvailability(user_id=user_id, **slot_data)
        db.add(slot)
        await db.commit()
        await db.refresh(slot)
        return slot

    @staticmethod
    async def get_user_slots(
        db: AsyncSession,
        user_id: int,
        include_inactive: bool = False,
    ) -> list[UserAvailability]:
        query = select(UserAvailability).where(UserAvailability.user_id == user_id)

        if not include_inactive:
            query = query.where(UserAvailability.is_active)

        query = query.order_by(
            UserAvailability.specific_date.desc().nullslast(),
            UserAvailability.day_of_week.asc().nullslast(),
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_slot_by_id(
        db: AsyncSession,
        slot_id: int,
        user_id: int | None = None,
    ) -> UserAvailability | None:
        query = select(UserAvailability).where(UserAvailability.id == slot_id)

        if user_id is not None:
            query = query.where(UserAvailability.user_id == user_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_slot(
        db: AsyncSession,
        slot: UserAvailability,
        update_data: dict[str, str | bool | None],
    ) -> UserAvailability:
        for key, value in update_data.items():
            if value is not None:
                setattr(slot, key, value)

        await db.commit()
        await db.refresh(slot)
        return slot

    @staticmethod
    async def delete_slot(
        db: AsyncSession,
        slot: UserAvailability,
        soft_delete: bool = True,
    ) -> None:
        if soft_delete:
            slot.is_active = False
            await db.commit()
        else:
            await db.delete(slot)
            await db.commit()

    @staticmethod
    async def get_public_availability(
        db: AsyncSession,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[UserAvailability]:
        query = select(UserAvailability).where(
            and_(
                UserAvailability.user_id == user_id,
                UserAvailability.is_active,
                UserAvailability.slot_type == "available",
            )
        )

        if start_date and end_date:
            query = query.where(
                or_(
                    UserAvailability.day_of_week.is_not(None),
                    and_(
                        UserAvailability.specific_date.is_not(None),
                        UserAvailability.specific_date >= start_date,
                        UserAvailability.specific_date <= end_date,
                    ),
                )
            )

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def block_time_for_transaction(
        db: AsyncSession,
        transaction_id: int,
        user_id: int,
        start_time: datetime,
        end_time: datetime,
        title: str,
    ) -> UserAvailability:
        blocked_slot = UserAvailability(
            user_id=user_id,
            slot_type="blocked",
            specific_date=start_time.date(),
            specific_start=start_time,
            specific_end=end_time,
            source="transaction",
            source_id=transaction_id,
            title=title,
            is_active=True,
        )

        db.add(blocked_slot)
        await db.commit()
        await db.refresh(blocked_slot)
        return blocked_slot

    @staticmethod
    async def remove_transaction_blocks(
        db: AsyncSession,
        transaction_id: int,
    ) -> None:
        query = select(UserAvailability).where(
            and_(
                UserAvailability.source == "transaction",
                UserAvailability.source_id == transaction_id,
            )
        )
        result = await db.execute(query)
        slots = result.scalars().all()

        for slot in slots:
            await db.delete(slot)

        await db.commit()

    @staticmethod
    async def check_time_available(
        db: AsyncSession,
        user_id: int,
        check_start: datetime,
        check_end: datetime,
    ) -> bool:
        query = select(UserAvailability).where(
            and_(
                UserAvailability.user_id == user_id,
                UserAvailability.is_active,
                UserAvailability.slot_type == "blocked",
                UserAvailability.specific_start.is_not(None),
                UserAvailability.specific_end.is_not(None),
                or_(
                    and_(
                        UserAvailability.specific_start <= check_start,
                        UserAvailability.specific_end > check_start,
                    ),
                    and_(
                        UserAvailability.specific_start < check_end,
                        UserAvailability.specific_end >= check_end,
                    ),
                    and_(
                        UserAvailability.specific_start >= check_start,
                        UserAvailability.specific_end <= check_end,
                    ),
                ),
            )
        )

        result = await db.execute(query)
        conflicts = result.scalars().first()

        return conflicts is None
