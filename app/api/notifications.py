from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Annotated

from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    NotificationRead,
    NotificationUpdate,
    NotificationStats,
    NotificationType,
)
from app.core.dependencies import get_current_user
from app.core.rate_limit_decorator import read_rate_limit

router = APIRouter()


@router.get(
    "/",
    response_model=list[NotificationRead],
    summary="Get user notifications",
)
@read_rate_limit("notification_listing")
async def get_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    unread_only: Annotated[bool, Query()] = False,
    type_filter: Annotated[NotificationType | None, Query()] = None,
):
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    if type_filter:
        query = query.where(Notification.type == type_filter)

    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    notifications = result.scalars().all()

    return [NotificationRead.model_validate(n) for n in notifications]


@router.get(
    "/stats",
    response_model=NotificationStats,
    summary="Get notification statistics",
)
async def get_notification_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    unread_count_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    )
    total_unread = unread_count_result.scalar() or 0

    # Unread count by type
    unread_by_type_result = await db.execute(
        select(Notification.type, func.count(Notification.id))
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .group_by(Notification.type)
    )
    unread_by_type = {
        notification_type: count
        for notification_type, count in unread_by_type_result.all()
    }

    latest_result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.is_read.asc(), Notification.created_at.desc())
        .limit(5)
    )
    latest_notifications = latest_result.scalars().all()

    return NotificationStats(
        total_unread=total_unread,
        unread_by_type=unread_by_type,
        latest_notifications=[
            NotificationRead.model_validate(n) for n in latest_notifications
        ],
    )


@router.put(
    "/{notification_id}",
    response_model=NotificationRead,
    summary="Update notification (mark as read/unread)",
)
async def update_notification(
    notification_id: int,
    notification_update: NotificationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this notification",
        )

    notification.is_read = notification_update.is_read
    await db.commit()
    await db.refresh(notification)

    return NotificationRead.model_validate(notification)


@router.post(
    "/mark-all-read",
    summary="Mark all notifications as read",
)
async def mark_all_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    type_filter: Annotated[NotificationType | None, Query()] = None,
):
    query = select(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    )

    if type_filter:
        query = query.where(Notification.type == type_filter)

    result = await db.execute(query)
    notifications = result.scalars().all()

    for notification in notifications:
        notification.is_read = True

    await db.commit()

    return {
        "message": f"Marked {len(notifications)} notifications as read",
        "count": len(notifications),
    }


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a notification",
)
async def delete_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this notification",
        )

    _ = await db.execute(delete(Notification).where(Notification.id == notification_id))
    await db.commit()


@router.delete(
    "/",
    summary="Delete all read notifications",
)
async def delete_all_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        delete(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read,
        )
    )
    await db.commit()

    return {
        "message": "Deleted all read notifications",
        "deleted_count": result.rowcount,
    }
