from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    File,
    UploadFile,
    Query,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserPublic, UserPrivate, UserAdmin
from app.services.privacy import PrivacyService
from app.services.file_service import FileUploadService
from app.core.dependencies import get_current_active_user, get_optional_current_user
from app.core.rate_limit_decorator import read_rate_limit
from app.core.auth import get_password_hash
from typing import Annotated

router = APIRouter()


UPLOAD_DIR = Path("uploads/profile_images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("/", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(User).where(User.display_name == user.display_name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display name already registered",
        )

    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user_data = user.model_dump(exclude={"password"})
    user_data["password_hash"] = get_password_hash(user.password)

    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return UserPrivate.model_validate(db_user)


@router.get("/admin-list", response_model=list[UserAdmin])
async def list_users_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
    email_verified: bool | None = None,
):
    query = select(User)

    if search:
        query = query.where(
            User.display_name.ilike(f"%{search}%")
            | User.first_name.ilike(f"%{search}%")
            | User.last_name.ilike(f"%{search}%")
            | User.email.ilike(f"%{search}%")
        )

    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if is_admin is not None:
        query = query.where(User.is_admin == is_admin)
    if email_verified is not None:
        query = query.where(User.email_verified == email_verified)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    return users


@router.get("/{user_id}", response_model=UserPublic | UserPrivate)
@read_rate_limit("user_profile")
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
):
    viewer_id = current_user.id if current_user else None

    user_data = await PrivacyService.get_user_for_viewer(
        db=db, user_id=user_id, viewer_id=viewer_id
    )

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user_data


@router.put("/me", response_model=UserPrivate)
async def update_current_user(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if (
        user_update.display_name
        and user_update.display_name != current_user.display_name
    ):
        result = await db.execute(
            select(User).where(User.display_name == user_update.display_name)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Display name already taken",
            )

    update_data: dict[str, object] = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)

    try:
        await db.commit()
        await db.refresh(current_user)
        return UserPrivate.model_validate(current_user)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile",
        )


@router.post("/me/profile-image")
async def upload_profile_image(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_image: Annotated[UploadFile, File()],
):
    file_service = FileUploadService()

    try:
        _file_path, public_url = await file_service.upload_profile_image(
            profile_image, current_user.id
        )

        if current_user.profile_image_url:
            _ = await file_service.delete_profile_image(current_user.profile_image_url)

        current_user.profile_image_url = public_url
        await db.commit()

        return {
            "profile_image_url": public_url,
            "message": "Profile image uploaded successfully",
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to upload profile image")


@router.delete("/me/profile-image")
async def delete_profile_image(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not current_user.profile_image_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No profile image to delete"
        )

    try:
        filename = current_user.profile_image_url.split("/")[-1]
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            file_path.unlink()

        current_user.profile_image_url = None

        await db.commit()
        await db.refresh(current_user)

        return {"message": "Profile image deleted successfully"}

    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile image",
        )


@router.get("/", response_model=list[UserPublic])
@read_rate_limit("user_search")
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    messages_enabled_only: Annotated[
        bool | None, Query(description="Only return users with messages enabled")
    ] = False,
):
    query = select(User).where(User.is_active)

    if search:
        query = query.where(
            User.display_name.ilike(f"%{search}%")
            | User.first_name.ilike(f"%{search}%")
            | User.last_name.ilike(f"%{search}%")
        )

    if messages_enabled_only:
        query = query.where(User.messages_enabled)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    filtered_users: list[UserPublic] = []
    for user in users:
        user_data = await PrivacyService._filter_public_user_data(user)
        filtered_users.append(user_data)

    return filtered_users


@router.get("/me/stats")
async def get_user_stats(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        events_attended = (
            len(current_user.participations)
            if hasattr(current_user, "participations")
            else 0
        )
        events_organized = (
            len(current_user.events) if hasattr(current_user, "events") else 0
        )
        services_offered = (
            len(current_user.services) if hasattr(current_user, "services") else 0
        )

        community_score = min(
            100,
            (events_attended * 5) + (events_organized * 10) + (services_offered * 8),
        )

        return {
            "events_attended": events_attended,
            "events_organized": events_organized,
            "services_offered": services_offered,
            "total_connections": events_attended + events_organized,
            "community_score": community_score,
        }
    except Exception:
        return {
            "events_attended": 0,
            "events_organized": 0,
            "services_offered": 0,
            "total_connections": 0,
            "community_score": 0,
        }


@router.get("/me/activities")
async def get_user_activities() -> dict[str, list[dict[str, object]]]:
    return {"recent_events": [], "active_services": [], "recent_forum_posts": []}
