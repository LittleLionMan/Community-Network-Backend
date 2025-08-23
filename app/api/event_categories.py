from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List

from app.database import get_db
from app.models.event import EventCategory
from app.schemas.event import EventCategoryCreate, EventCategoryRead
from app.core.dependencies import get_current_admin_user
from app.schemas.common import ErrorResponse

router = APIRouter()

@router.get(
    "/",
    response_model=List[EventCategoryRead],
    summary="Get all event categories",
    description="Public endpoint to retrieve all available event categories"
)
async def get_event_categories(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all event categories (public endpoint)"""
    result = await db.execute(
        select(EventCategory).offset(skip).limit(limit)
    )
    categories = result.scalars().all()
    return categories

@router.get(
    "/{category_id}",
    response_model=EventCategoryRead,
    responses={
        404: {"model": ErrorResponse, "description": "Category not found"}
    }
)
async def get_event_category(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get specific event category"""
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    return category

# Admin endpoints
@router.post(
    "/admin",
    response_model=EventCategoryRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Category name already exists"},
        403: {"model": ErrorResponse, "description": "Admin access required"}
    }
)
async def create_event_category(
    category_data: EventCategoryCreate,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new event category (admin only)"""
    # Check if category name already exists
    result = await db.execute(
        select(EventCategory).where(EventCategory.name == category_data.name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists"
        )

    # Create category
    db_category = EventCategory(**category_data.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)

    return db_category

@router.put(
    "/admin/{category_id}",
    response_model=EventCategoryRead,
    responses={
        400: {"model": ErrorResponse, "description": "Category name already exists"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        404: {"model": ErrorResponse, "description": "Category not found"}
    }
)
async def update_event_category(
    category_id: int,
    category_data: EventCategoryCreate,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update event category (admin only)"""
    # Find category
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Check if new name conflicts with existing (excluding current)
    if category_data.name != category.name:
        result = await db.execute(
            select(EventCategory).where(
                EventCategory.name == category_data.name,
                EventCategory.id != category_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name already exists"
            )

    # Update category
    update_data = category_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)

    return category

@router.delete(
    "/admin/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse, "description": "Admin access required"},
        404: {"model": ErrorResponse, "description": "Category not found"},
        409: {"model": ErrorResponse, "description": "Category is in use by events"}
    }
)
async def delete_event_category(
    category_id: int,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete event category (admin only)"""
    # Find category
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Check if category is used by any events
    from app.models.event import Event
    result = await db.execute(
        select(Event).where(Event.category_id == category_id)
    )
    events_count = len(result.scalars().all())

    if events_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete category. {events_count} events are using this category."
        )

    # Delete category
    await db.execute(
        delete(EventCategory).where(EventCategory.id == category_id)
    )
    await db.commit()
