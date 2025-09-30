from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from typing import Annotated, cast
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.event import EventCategory, Event
from app.schemas.event import EventCategoryCreate, EventCategoryRead
from app.core.dependencies import get_current_admin_user
from app.schemas.common import ErrorResponse
from app.core.logging import SecurityLogger


class EventCategoryStatsRead(BaseModel):
    id: int
    name: str
    description: str | None
    event_count: int
    created_at: str
    can_delete: bool


class CreateDefaultCategoriesResponse(BaseModel):
    message: str
    categories_created: int
    categories: list[EventCategoryStatsRead]


router = APIRouter()


@router.get(
    "/",
    response_model=list[EventCategoryRead],
    summary="Get all event categories",
    description="Public endpoint to retrieve all available event categories",
)
async def get_event_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
):
    result = await db.execute(select(EventCategory).offset(skip).limit(limit))
    categories = result.scalars().all()
    return categories


@router.get(
    "/admin",
    response_model=list[EventCategoryStatsRead],
    responses={403: {"model": ErrorResponse, "description": "Admin access required"}},
)
async def get_admin_event_categories(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[EventCategoryStatsRead]:
    SecurityLogger.log_admin_action(
        request, admin_user_id=current_admin.id, action="view_event_categories"
    )

    result = await db.execute(
        select(EventCategory, func.count(Event.id).label("event_count"))
        .outerjoin(Event, EventCategory.id == Event.category_id)
        .group_by(EventCategory.id)
        .order_by(EventCategory.name)
    )

    categories_with_stats: list[EventCategoryStatsRead] = []
    for row in result.all():
        category = cast(EventCategory, row[0])
        event_count = cast(int, row[1]) or 0
        stats = EventCategoryStatsRead(
            id=category.id,
            name=category.name,
            description=category.description,
            event_count=event_count or 0,
            created_at=category.created_at.isoformat()
            if hasattr(category, "created_at")
            else datetime.now().isoformat(),
            can_delete=(event_count or 0) == 0,
        )
        categories_with_stats.append(stats)

    return categories_with_stats


@router.get(
    "/{category_id}",
    response_model=EventCategoryRead,
    responses={404: {"model": ErrorResponse, "description": "Category not found"}},
)
async def get_event_category(
    category_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    return category


@router.post(
    "/admin",
    response_model=EventCategoryRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Category name already exists"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
    },
)
async def create_event_category(
    category_data: EventCategoryCreate, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(EventCategory).where(EventCategory.name == category_data.name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists",
        )

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
        404: {"model": ErrorResponse, "description": "Category not found"},
    },
)
async def update_event_category(
    category_id: int,
    category_data: EventCategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    if category_data.name != category.name:
        result = await db.execute(
            select(EventCategory).where(
                EventCategory.name == category_data.name,
                EventCategory.id != category_id,
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

    return category


@router.delete(
    "/admin/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse, "description": "Admin access required"},
        404: {"model": ErrorResponse, "description": "Category not found"},
        409: {"model": ErrorResponse, "description": "Category is in use by events"},
    },
)
async def delete_event_category(
    category_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    from app.models.event import Event

    result = await db.execute(select(Event).where(Event.category_id == category_id))
    events_count = len(result.scalars().all())

    if events_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete category. {events_count} events are using this category.",
        )

    _ = await db.execute(delete(EventCategory).where(EventCategory.id == category_id))
    await db.commit()


@router.post(
    "/admin/create-defaults",
    response_model=CreateDefaultCategoriesResponse,
    responses={403: {"model": ErrorResponse, "description": "Admin access required"}},
)
async def create_default_event_categories(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateDefaultCategoriesResponse:
    SecurityLogger.log_admin_action(
        request, admin_user_id=current_admin.id, action="create_default_categories"
    )

    default_categories = [
        {"name": "Sport", "description": "Sportliche Aktivitäten und Events"},
        {
            "name": "Kultur",
            "description": "Kulturelle Veranstaltungen, Kunst und Musik",
        },
        {"name": "Bildung", "description": "Workshops, Kurse und Lernveranstaltungen"},
        {
            "name": "Community",
            "description": "Gemeinschaftsveranstaltungen und Treffen",
        },
        {"name": "Food & Drinks", "description": "Kulinarische Events und Kochkurse"},
        {"name": "Outdoor", "description": "Aktivitäten in der Natur und im Freien"},
        {"name": "Gaming", "description": "Spieleabende und Gaming-Events"},
        {"name": "Business", "description": "Berufliche Netzwerk-Events und Seminare"},
    ]

    created_categories: list[EventCategoryStatsRead] = []
    categories_created = 0

    for cat_data in default_categories:
        result = await db.execute(
            select(EventCategory).where(EventCategory.name == cat_data["name"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            db_category = EventCategory(**cat_data)
            db.add(db_category)
            categories_created += 1

    await db.commit()

    if categories_created > 0:
        result = await db.execute(
            select(EventCategory, func.count(Event.id).label("event_count"))
            .outerjoin(Event, EventCategory.id == Event.category_id)
            .group_by(EventCategory.id)
            .order_by(EventCategory.name)
        )

        for row in result.all():
            category = cast(EventCategory, row[0])
            event_count = cast(int, row[1]) or 0

            stats = EventCategoryStatsRead(
                id=category.id,
                name=category.name,
                description=category.description,
                event_count=event_count,
                created_at=category.created_at.isoformat()
                if hasattr(category, "created_at")
                else datetime.now().isoformat(),
                can_delete=True,
            )
            created_categories.append(stats)

    return CreateDefaultCategoriesResponse(
        message=f"Successfully created {categories_created} default categories",
        categories_created=categories_created,
        categories=created_categories,
    )
