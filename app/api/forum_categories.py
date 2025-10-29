from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.forum import ForumCategory, ForumThread, ForumPost, ForumThreadView
from app.models.user import User
from app.schemas.forum import (
    ForumCategoryCreate,
    ForumCategoryRead,
    ForumCategoryUpdate,
    ForumThreadSummary,
    ForumPostSummary,
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user
from typing import Annotated

router = APIRouter()


@router.get(
    "/", response_model=list[ForumCategoryRead], summary="Get all forum categories"
)
async def get_forum_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: Annotated[
        bool, Query(description="Include inactive categories")
    ] = False,
) -> list[ForumCategoryRead]:
    query = select(ForumCategory)

    if not include_inactive:
        query = query.where(ForumCategory.is_active)

    query = query.order_by(ForumCategory.display_order.asc(), ForumCategory.name.asc())

    result = await db.execute(query)
    categories = result.scalars().all()

    enriched_categories: list[ForumCategoryRead] = []
    for category in categories:
        thread_count_result = await db.execute(
            select(func.count(ForumThread.id)).where(
                ForumThread.category_id == category.id
            )
        )
        thread_count = thread_count_result.scalar() or 0

        latest_thread_result = await db.execute(
            select(ForumThread)
            .where(ForumThread.category_id == category.id)
            .options(selectinload(ForumThread.creator))
            .order_by(desc(ForumThread.created_at))
            .limit(1)
        )
        latest_thread = latest_thread_result.scalar_one_or_none()

        latest_activity_post_result = await db.execute(
            select(ForumPost)
            .join(ForumThread, ForumPost.thread_id == ForumThread.id)
            .where(ForumThread.category_id == category.id)
            .options(selectinload(ForumPost.author))
            .order_by(desc(ForumPost.created_at))
            .limit(1)
        )
        latest_activity_post = latest_activity_post_result.scalar_one_or_none()

        latest_activity_thread = None
        latest_activity_at = None

        if latest_activity_post:
            latest_activity_thread_result = await db.execute(
                select(ForumThread)
                .where(ForumThread.id == latest_activity_post.thread_id)
                .options(selectinload(ForumThread.creator))
            )
            latest_activity_thread = latest_activity_thread_result.scalar_one_or_none()
            latest_activity_at = latest_activity_post.created_at

        category_dict = ForumCategoryRead.model_validate(category).model_dump()
        category_dict["thread_count"] = thread_count

        if latest_thread:
            category_dict["latest_thread"] = ForumThreadSummary.model_validate(
                latest_thread
            )

        if latest_activity_thread:
            category_dict["latest_activity_thread"] = ForumThreadSummary.model_validate(
                latest_activity_thread
            )

        if latest_activity_post:
            category_dict["latest_activity_post"] = ForumPostSummary.model_validate(
                latest_activity_post
            )

        category_dict["latest_activity_at"] = latest_activity_at

        enriched_categories.append(ForumCategoryRead.model_validate(category_dict))

    return enriched_categories


@router.get(
    "/unread-counts",
    summary="Get unread thread counts per category",
    description="Returns the number of unread threads in each category for the current user",
)
async def get_unread_counts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    categories_result = await db.execute(
        select(ForumCategory.id).where(ForumCategory.is_active)
    )
    category_ids = [cat_id for (cat_id,) in categories_result.all()]

    if not category_ids:
        return {}

    threads_result = await db.execute(
        select(
            ForumThread.id,
            ForumThread.category_id,
            func.max(ForumPost.created_at).label("latest_post"),
        )
        .outerjoin(ForumPost, ForumPost.thread_id == ForumThread.id)
        .where(ForumThread.category_id.in_(category_ids))
        .group_by(ForumThread.id, ForumThread.category_id)
    )
    threads_data = {
        thread_id: {"category_id": cat_id, "latest_post": latest_post}
        for thread_id, cat_id, latest_post in threads_result.all()
    }

    if not threads_data:
        return {str(cat_id): 0 for cat_id in category_ids}

    thread_ids = list(threads_data.keys())
    views_result = await db.execute(
        select(ForumThreadView.thread_id, ForumThreadView.last_viewed_at).where(
            ForumThreadView.user_id == current_user.id,
            ForumThreadView.thread_id.in_(thread_ids),
        )
    )
    views = {thread_id: last_viewed for thread_id, last_viewed in views_result.all()}

    unread_counts: dict[int, int] = {cat_id: 0 for cat_id in category_ids}

    for thread_id, data in threads_data.items():
        category_id = data["category_id"]
        latest_post = data["latest_post"]
        last_viewed = views.get(thread_id)

        is_unread = last_viewed is None or (
            latest_post is not None and latest_post > last_viewed
        )

        if is_unread:
            unread_counts[category_id] += 1

    return {str(cat_id): count for cat_id, count in unread_counts.items()}


@router.get(
    "/{category_id}",
    response_model=ForumCategoryRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_forum_category(
    category_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    thread_count_result = await db.execute(
        select(func.count(ForumThread.id)).where(ForumThread.category_id == category.id)
    )
    thread_count = thread_count_result.scalar() or 0

    category_dict = ForumCategoryRead.model_validate(category).model_dump()
    category_dict["thread_count"] = thread_count

    return ForumCategoryRead.model_validate(category_dict)


@router.post(
    "/admin",
    response_model=ForumCategoryRead,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def create_forum_category(
    category_data: ForumCategoryCreate, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.name == category_data.name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists",
        )

    db_category = ForumCategory(**category_data.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)

    category_dict = ForumCategoryRead.model_validate(db_category).model_dump()
    category_dict["thread_count"] = 0

    return ForumCategoryRead.model_validate(category_dict)


@router.put(
    "/admin/{category_id}",
    response_model=ForumCategoryRead,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def update_forum_category(
    category_id: int,
    category_data: ForumCategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    if category_data.name and category_data.name != category.name:
        result = await db.execute(
            select(ForumCategory).where(
                ForumCategory.name == category_data.name,
                ForumCategory.id != category_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name already exists",
            )

    update_data: dict[str, object] = category_data.model_dump(exclude_unset=True)
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

    return ForumCategoryRead.model_validate(category_dict)


@router.delete(
    "/admin/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def delete_forum_category(
    category_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    result = await db.execute(
        select(func.count(ForumThread.id)).where(ForumThread.category_id == category_id)
    )
    threads_count = result.scalar() or 0

    if threads_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete category. {threads_count} threads exist in this category.",
        )

    _ = await db.execute(delete(ForumCategory).where(ForumCategory.id == category_id))
    await db.commit()
