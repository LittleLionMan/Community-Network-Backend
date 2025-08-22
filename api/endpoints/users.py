from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from ...database import get_db
from ...models.user import User
from ...schemas.user import UserCreate, UserUpdate, UserPublic, UserPrivate
from ...services.privacy import PrivacyService
from ...core.auth import get_current_user, get_current_user_optional

router = APIRouter()

@router.post("/users/", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):

    if db.query(User).filter(User.display_name == user.display_name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display name already registered"
        )

    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    db_user = User(**user.dict(exclude={"password"}), password_hash="hashed_password")
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return UserPrivate.from_orm(db_user)

@router.get("/users/{user_id}", response_model=UserPublic | UserPrivate)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):

    viewer_id = current_user.id if current_user else None

    user_data = PrivacyService.get_user_for_viewer(
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

@router.put("/users/me", response_model=UserPrivate)
def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if user_update.display_name and user_update.display_name != current_user.display_name:
        if db.query(User).filter(User.display_name == user_update.display_name).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Display name already taken"
            )

    update_data = user_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    return UserPrivate.from_orm(current_user)

@router.get("/users/", response_model=List[UserPublic])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):

    users = db.query(User).offset(skip).limit(limit).all()
    viewer_id = current_user.id if current_user else None

    filtered_users = []
    for user in users:
        if viewer_id and viewer_id == user.id:
            filtered_users.append(PrivacyService._filter_public_user_data(user))
        else:
            filtered_users.append(PrivacyService._filter_public_user_data(user))

    return filtered_users
