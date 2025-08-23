from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserPublic, UserPrivate
from app.services.privacy import PrivacyService
from app.core.dependencies import get_current_user, get_optional_current_user

router = APIRouter()

@router.post("/", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    # Check display name
    result = await db.execute(select(User).where(User.display_name == user.display_name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display name already registered"
        )

    # Check email
    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    user_data = user.model_dump(exclude={"password"})
    user_data["password_hash"] = "hashed_password"  # TODO: Implement proper hashing

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check display name if changed
    if user_update.display_name and user_update.display_name != current_user.display_name:
        result = await db.execute(
            select(User).where(User.display_name == user_update.display_name)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Display name already taken"
            )

    # Update user
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return UserPrivate.model_validate(current_user)

@router.get("/", response_model=List[UserPublic])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    result = await db.execute(
        select(User).offset(skip).limit(limit)
    )
    users = result.scalars().all()

    viewer_id = current_user.id if current_user else None

    filtered_users = []
    for user in users:
        if viewer_id and viewer_id == user.id:
            filtered_users.append(await PrivacyService._filter_public_user_data(user))
        else:
            filtered_users.append(await PrivacyService._filter_public_user_data(user))

    return filtered_users
