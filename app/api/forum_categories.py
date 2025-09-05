from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, desc
from sqlalchemy.orm import selectinload
from typing import List

from app.database import get_db
from app.models.forum import ForumCategory, ForumThread
from app.schemas.forum import (
    ForumCategoryCreate, ForumCategoryRead, ForumCategoryUpdate,
    ForumThreadSummary
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_admin_user

router = APIRouter()

@router.get(
    "/",
    response_model=List[ForumCategoryRead],
    summary="Get all forum categories"
)
async def get_forum_categories(
    include_inactive: bool = Query(False, description="Include inactive categories"),
    db: AsyncSession = Depends(get_db)
):
    query = select(ForumCategory)

    if not include_inactive:
        query = query.where(ForumCategory.is_active == True)

    query = query.order_by(ForumCategory.display_order.asc(), ForumCategory.name.asc())

    result = await db.execute(query)
    categories = result.scalars().all()

    enriched_categories = []
    for category in categories:
        thread_count_result = await db.execute(
            select(func.count(ForumThread.id)).where(ForumThread.category_id == category.id)
        )
        thread_count = thread_count_result.scalar() or 0

        latest_thread_result = await db.execute(
            select(ForumThread).where(ForumThread.category_id == category.id)
            .options(selectinload(ForumThread.creator))
            .order_by(desc(ForumThread.created_at)).limit(1)
        )
        latest_thread = latest_thread_result.scalar_one_or_none()

        category_dict = ForumCategoryRead.model_validate(category).model_dump()
        category_dict["thread_count"] = thread_count
        if latest_thread:
            category_dict["latest_thread"] = ForumThreadSummary.model_validate(latest_thread)

        enriched_categories.append(ForumCategoryRead(**category_dict))

    return enriched_categories

@router.get(
    "/{category_id}",
    response_model=ForumCategoryRead,
    responses={404: {"model": ErrorResponse}}
)
async def get_forum_category(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    thread_count_result = await db.execute(
        select(func.count(ForumThread.id)).where(ForumThread.category_id == category.id)
    )
    thread_count = thread_count_result.scalar() or 0

    category_dict = ForumCategoryRead.model_validate(category).model_dump()
    category_dict["thread_count"] = thread_count

    return ForumCategoryRead(**category_dict)

@router.post(
    "/admin",
    response_model=ForumCategoryRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse}
    }
)
async def create_forum_category(
    category_data: ForumCategoryCreate,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.name == category_data.name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists"
        )

    db_category = ForumCategory(**category_data.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)

    category_dict = ForumCategoryRead.model_validate(db_category).model_dump()
    category_dict["thread_count"] = 0

    return ForumCategoryRead(**category_dict)

@router.put(
    "/admin/{category_id}",
    response_model=ForumCategoryRead,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse}
    }
)
async def update_forum_category(
    category_id: int,
    category_data: ForumCategoryUpdate,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    if category_data.name and category_data.name != category.name:
        result = await db.execute(
            select(ForumCategory).where(
                ForumCategory.name == category_data.name,
                ForumCategory.id != category_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name already exists"
            )

    update_data = category_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)

    thread_count_result = await db.execute(
        select(func.count(ForumThread.id)).where(ForumThread.category_id == category.id)
    )
    thread_count = thread_count_result.scalar() or 0

    category_dict = ForumCategoryRead.model_validate(category).model_dump()
    category_dict["thread_count"] = thread_count

    return ForumCategoryRead(**category_dict)

@router.delete(
    "/admin/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse}
    }
)
async def delete_forum_category(
    category_id: int,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    result = await db.execute(
        select(func.count(ForumThread.id)).where(ForumThread.category_id == category_id)
    )
    threads_count = result.scalar() or 0

    if threads_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete category. {threads_count} threads exist in this category."
        )

    await db.execute(
        delete(ForumCategory).where(ForumCategory.id == category_id)
    )
    await db.commit()
