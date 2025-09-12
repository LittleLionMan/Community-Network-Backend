from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.event import Event, EventCategory, EventParticipation
from app.models.user import User
from app.schemas.event import (
    EventCreate, EventRead, EventUpdate, EventSummary, EventParticipationRead
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_current_admin_user, get_optional_current_user
from app.core.rate_limit_decorator import event_create_rate_limit, read_rate_limit
from app.models.enums import ParticipationStatus
from app.services.event_service import EventService

router = APIRouter()

@router.get(
    "/",
    response_model=List[EventSummary],
    summary="Get all events",
    description="Public endpoint to retrieve all active events with pagination"
)
@read_rate_limit("event_listing")
async def get_events(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None),
    upcoming_only: bool = Query(True, description="Show only upcoming events"),
    db: AsyncSession = Depends(get_db)
):
    query = select(Event).where(Event.is_active == True)

    if category_id:
        query = query.where(Event.category_id == category_id)

    if upcoming_only:
        from datetime import datetime
        query = query.where(Event.start_datetime > datetime.now())

    query = query.order_by(Event.start_datetime.asc()).offset(skip).limit(limit)

    query = query.options(
        selectinload(Event.creator),
        selectinload(Event.category),
        selectinload(Event.participations)
    )

    result = await db.execute(query)
    events = result.scalars().all()

    event_summaries = []
    for event in events:
        event_dict = EventSummary.model_validate(event, from_attributes=True).model_dump()
        participant_count = len([p for p in event.participations
                               if p.status == ParticipationStatus.REGISTERED])
        event_dict["participant_count"] = participant_count
        event_summaries.append(EventSummary(**event_dict))

    return event_summaries

@router.get(
    "/{event_id}",
    response_model=EventRead,
    responses={
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
@read_rate_limit("event_listing")
async def get_event(
    request: Request,
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    query = select(Event).where(
        Event.id == event_id,
        Event.is_active == True
    ).options(
        selectinload(Event.creator),
        selectinload(Event.category),
        selectinload(Event.participations).selectinload(EventParticipation.user)
    )

    result = await db.execute(query)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    if not event.creator:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event creator data missing"
        )

    event_dict = EventRead.model_validate(event, from_attributes=True).model_dump()
    participant_count = len([p for p in event.participations
                           if p.status == ParticipationStatus.REGISTERED])
    event_dict["participant_count"] = participant_count
    event_dict["is_full"] = (event.max_participants is not None and
                            participant_count >= event.max_participants)

    return EventRead(**event_dict)

@router.post(
    "/",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid event data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Category not found"}
    }
)
@event_create_rate_limit
async def create_event(
    request: Request,
    event_data: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(EventCategory).where(EventCategory.id == event_data.category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event category not found"
        )

    event_dict = event_data.model_dump()
    event_dict["creator_id"] = current_user.id

    db_event = Event(**event_dict)
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event, ["creator", "category"])

    return EventRead.model_validate(db_event, from_attributes=True)

@router.put(
    "/{event_id}",
    response_model=EventRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid event data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this event"},
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
async def update_event(
    event_id: int,
    event_data: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Event).where(Event.id == event_id, Event.is_active == True)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    if event.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this event"
        )

    if event_data.category_id and event_data.category_id != event.category_id:
        result = await db.execute(
            select(EventCategory).where(EventCategory.id == event_data.category_id)
        )
        category = result.scalar_one_or_none()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event category not found"
            )

    update_data = event_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    await db.commit()
    await db.refresh(event, ["creator", "category"])

    return EventRead.model_validate(event, from_attributes=True)

@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to delete this event"},
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
async def delete_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Event).where(Event.id == event_id, Event.is_active == True)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    if event.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this event"
        )

    event.is_active = False
    await db.commit()

@router.post(
    "/{event_id}/join",
    response_model=EventParticipationRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Cannot join event (full, past, already joined)"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
async def join_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    event_service = EventService(db)

    result = await db.execute(
        select(Event).where(
            Event.id == event_id,
            Event.is_active == True
        ).options(selectinload(Event.participations))
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    can_join, reason = await event_service.can_join_event(event, current_user)
    if not can_join:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason
        )

    result = await db.execute(
        select(EventParticipation).where(
            EventParticipation.event_id == event_id,
            EventParticipation.user_id == current_user.id
        )
    )
    existing_participation = result.scalar_one_or_none()

    if existing_participation:
        if existing_participation.status == ParticipationStatus.CANCELLED:
            existing_participation.status = ParticipationStatus.REGISTERED
            await db.commit()
            await db.refresh(existing_participation, ["user", "status_updated_at", "registered_at"])
            return EventParticipationRead.model_validate(existing_participation, from_attributes=True)

    participation = EventParticipation(
        event_id=event_id,
        user_id=current_user.id,
        status=ParticipationStatus.REGISTERED
    )

    db.add(participation)
    await db.commit()
    await db.refresh(participation, ["user", "status_updated_at", "registered_at"])

    return EventParticipationRead.model_validate(participation, from_attributes=True)

@router.delete(
    "/{event_id}/join",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"model": ErrorResponse, "description": "Not participating in this event"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
async def leave_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    result = await db.execute(
        select(EventParticipation).where(
            EventParticipation.event_id == event_id,
            EventParticipation.user_id == current_user.id,
            EventParticipation.status == ParticipationStatus.REGISTERED
        )
    )
    participation = result.scalar_one_or_none()

    if not participation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not participating in this event"
        )

    participation.status = ParticipationStatus.CANCELLED
    await db.commit()

@router.get(
    "/{event_id}/participants",
    response_model=List[EventParticipationRead],
    responses={
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
async def get_event_participants(
    event_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Event).where(Event.id == event_id, Event.is_active == True)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    result = await db.execute(
        select(EventParticipation).where(
            EventParticipation.event_id == event_id,
            EventParticipation.status == ParticipationStatus.REGISTERED
        ).options(selectinload(EventParticipation.user))
    )
    participations = result.scalars().all()

    return [EventParticipationRead.model_validate(p, from_attributes=True) for p in participations]

@router.get(
    "/my/created",
    response_model=List[EventSummary],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_created_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Event).where(
            Event.creator_id == current_user.id,
            Event.is_active == True
        ).options(
            selectinload(Event.creator),
            selectinload(Event.category)
        ).order_by(Event.start_datetime.asc()).offset(skip).limit(limit)
    )
    events = result.scalars().all()

    return [EventSummary.model_validate(event, from_attributes=True) for event in events]

@router.get(
    "/my/joined",
    response_model=List[EventParticipationRead],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_joined_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(EventParticipation).where(
            EventParticipation.user_id == current_user.id,
            EventParticipation.status == ParticipationStatus.REGISTERED
        ).join(Event).where(Event.is_active == True)
        .options(
            selectinload(EventParticipation.user),
            selectinload(EventParticipation.event).selectinload(Event.category)
        ).order_by(Event.start_datetime.asc()).offset(skip).limit(limit)
    )
    participations = result.scalars().all()

    return [EventParticipationRead.model_validate(p, from_attributes=True) for p in participations]

@router.get(
    "/my/stats",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_event_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    event_service = EventService(db)
    stats = await event_service.get_user_event_history(current_user.id)
    return stats

@router.post(
    "/{event_id}/mark-attendance",
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse, "description": "Admin access required"},
        404: {"model": ErrorResponse, "description": "Event not found"}
    }
)
async def mark_attendance(
    event_id: int,
    user_ids: List[int],
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):

    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    await db.execute(
        update(EventParticipation)
        .where(
            EventParticipation.event_id == event_id,
            EventParticipation.user_id.in_(user_ids),
            EventParticipation.status == ParticipationStatus.REGISTERED
        )
        .values(status=ParticipationStatus.ATTENDED)
    )

    await db.commit()

    return {"message": f"Marked {len(user_ids)} participants as attended"}

    @router.post(
        "/{event_id}/process-completion",
        status_code=status.HTTP_200_OK,
        responses={
            403: {"model": ErrorResponse, "description": "Admin access required"},
            404: {"model": ErrorResponse, "description": "Event not found"}
        }
    )
    async def process_event_completion(
        event_id: int,
        background_tasks: BackgroundTasks,
        current_admin: User = Depends(get_current_admin_user),
        db: AsyncSession = Depends(get_db)
    ):

        event_service = EventService(db)
        background_tasks.add_task(event_service.auto_mark_attendance, event_id)

        return {"message": "Event completion processing started"}
