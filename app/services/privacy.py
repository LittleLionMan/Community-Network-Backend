from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.user import User
from ..schemas.user import UserPublic, UserPrivate

class PrivacyService:

    @staticmethod
    async def get_user_for_viewer(
        db: AsyncSession,
        user_id: int,
        viewer_id: Optional[int] = None
    ) -> Optional[UserPublic | UserPrivate]:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        if viewer_id and viewer_id == user_id:
            return UserPrivate.model_validate(user)

        return await PrivacyService._filter_public_user_data(user)

    @staticmethod
    async def _filter_public_user_data(user: User) -> UserPublic:
        user_data = {
            "id": user.id,
            "display_name": user.display_name
        }

        # Conditional Fields basierend auf Privacy-Settings
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

        return UserPublic(**user_data)
