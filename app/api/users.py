from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pathlib import Path
import uuid

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserPublic, UserPrivate
from app.services.privacy import PrivacyService
from app.core.dependencies import get_current_active_user, get_optional_current_user
from app.core.auth import get_password_hash

router = APIRouter()

UPLOAD_DIR = Path("uploads/profile_images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

@router.post("/", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.display_name == user.display_name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display name already registered"
        )

    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    user_data = user.model_dump(exclude={"password"})
    user_data["password_hash"] = get_password_hash(user.password)

    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return UserPrivate.model_validate(db_user)

@router.get("/{user_id}", response_model=UserPublic | UserPrivate)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    viewer_id = current_user.id if current_user else None

    user_data = await PrivacyService.get_user_for_viewer(
        db=db,
        user_id=user_id,
        viewer_id=viewer_id
    )

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user_data

@router.put("/me", response_model=UserPrivate)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if user_update.display_name and user_update.display_name != current_user.display_name:
        result = await db.execute(
            select(User).where(User.display_name == user_update.display_name)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Display name already taken"
            )

    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)

    try:
        await db.commit()
        await db.refresh(current_user)
        return UserPrivate.model_validate(current_user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )

@router.post("/me/profile-image")
async def upload_profile_image(
    profile_image: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not profile_image.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )

    file_ext = Path(profile_image.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Supported: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_content = await profile_image.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size: 5MB"
        )

    file_path = None

    try:
        file_id = str(uuid.uuid4())
        filename = f"{current_user.id}_{file_id}{file_ext}"
        file_path = UPLOAD_DIR / filename

        if current_user.profile_image_url:
            old_filename = current_user.profile_image_url.split('/')[-1]
            old_file_path = UPLOAD_DIR / old_filename
            if old_file_path.exists():
                old_file_path.unlink()

        with open(file_path, "wb") as buffer:
            buffer.write(file_content)

        profile_image_url = f"/uploads/profile_images/{filename}"
        current_user.profile_image_url = profile_image_url

        await db.commit()
        await db.refresh(current_user)

        return {
            "profile_image_url": profile_image_url,
            "message": "Profile image uploaded successfully"
        }

    except Exception as e:
        await db.rollback()
        if file_path and file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload profile image"
        )

@router.delete("/me/profile-image")
async def delete_profile_image(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.profile_image_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile image to delete"
        )

    try:
        filename = current_user.profile_image_url.split('/')[-1]
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            file_path.unlink()

        current_user.profile_image_url = None

        await db.commit()
        await db.refresh(current_user)

        return {"message": "Profile image deleted successfully"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile image"
        )

@router.get("/", response_model=List[UserPublic])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    query = select(User).where(User.is_active == True)

    if search:
        query = query.where(
            User.display_name.ilike(f"%{search}%") |
            User.first_name.ilike(f"%{search}%") |
            User.last_name.ilike(f"%{search}%")
        )

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    filtered_users = []
    for user in users:
        user_data = await PrivacyService._filter_public_user_data(user)
        filtered_users.append(user_data)

    return filtered_users

@router.get("/me/stats")
async def get_user_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        events_attended = len(current_user.participations) if hasattr(current_user, 'participations') else 0
        events_organized = len(current_user.events) if hasattr(current_user, 'events') else 0
        services_offered = len(current_user.services) if hasattr(current_user, 'services') else 0

        community_score = min(100, (events_attended * 5) + (events_organized * 10) + (services_offered * 8))

        return {
            "events_attended": events_attended,
            "events_organized": events_organized,
            "services_offered": services_offered,
            "total_connections": events_attended + events_organized,
            "community_score": community_score
        }
    except Exception:
        return {
            "events_attended": 0,
            "events_organized": 0,
            "services_offered": 0,
            "total_connections": 0,
            "community_score": 0
        }

@router.get("/me/activities")
async def get_user_activities(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    return {
        "recent_events": [],
        "active_services": [],
        "recent_forum_posts": []
    }
