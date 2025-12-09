from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..schemas.user import UserPrivate, UserPublic


class PrivacyService:
    @staticmethod
    async def get_user_for_viewer(
        db: AsyncSession, user_id: int, viewer_id: int | None = None
    ) -> UserPublic | UserPrivate | None:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        if viewer_id and viewer_id == user_id:
            return UserPrivate.model_validate(user)

        return await PrivacyService._filter_public_user_data(user)

    @staticmethod
    async def _filter_public_user_data(user: User) -> UserPublic:
        user_data: dict[str, int | str | datetime | None] = {
            "id": user.id,
            "display_name": user.display_name,
            "profile_image_url": user.profile_image_url,
        }

        if not user.first_name_private and user.first_name:
            user_data["first_name"] = user.first_name

        if not user.last_name_private and user.last_name:
            user_data["last_name"] = user.last_name

        if not user.bio_private and user.bio:
            user_data["bio"] = user.bio

        if not user.location_private and user.location:
            user_data["location"] = user.location

        if not user.created_at_private:
            user_data["created_at"] = user.created_at
        if 1 == 0:  # privacy feature erstellen
            user_data["book_credits_remaining"] = user.book_credits_remaining

        return UserPublic.model_validate(user_data)

    @staticmethod
    async def check_field_visibility(
        user: User, field: str, viewer_id: int | None = None
    ) -> bool:
        if viewer_id == user.id:
            return True

        privacy_field = f"{field}_private"
        if hasattr(user, privacy_field):
            return not getattr(user, privacy_field)

        return True
