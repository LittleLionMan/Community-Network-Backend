from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from typing import Annotated

from app.database import get_db
from app.models.comment import Comment
from app.models.event import Event
from app.models.service import Service
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead, CommentUpdate
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user
from app.core.rate_limit_decorator import comment_rate_limit, read_rate_limit
from app.services.moderation_service import ModerationService

router = APIRouter()


@router.get(
    "/",
    response_model=list[CommentRead],
    summary="Get comments",
    description="Get comments for events, services, or forum threads with optional parent filtering",
)
@read_rate_limit("general_api")
async def get_comments(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Annotated[int | None, Query()] = None,
    service_id: Annotated[int | None, Query()] = None,
    parent_id: Annotated[
        int | None, Query(description="Get replies to specific comment")
    ] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    if not any([event_id, service_id]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify event_id or service_id",
        )

    query = select(Comment)

    if event_id:
        query = query.where(Comment.event_id == event_id)
    if service_id:
        query = query.where(Comment.service_id == service_id)
    if parent_id:
        query = query.where(Comment.parent_id == parent_id)
    else:
        query = query.where(Comment.parent_id.is_(None))

    query = (
        query.options(
            selectinload(Comment.author),
            selectinload(Comment.replies).selectinload(Comment.author),
        )
        .order_by(Comment.created_at.asc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    comments = result.scalars().all()

    return [CommentRead.model_validate(comment) for comment in comments]


@router.get(
    "/{comment_id}",
    response_model=CommentRead,
    responses={404: {"model": ErrorResponse, "description": "Comment not found"}},
)
async def get_comment(comment_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    query = (
        select(Comment)
        .where(Comment.id == comment_id)
        .options(
            selectinload(Comment.author),
            selectinload(Comment.replies).selectinload(Comment.author),
        )
    )

    result = await db.execute(query)
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    return CommentRead.model_validate(comment)


@router.post(
    "/",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid comment data or content flagged",
        },
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Parent resource not found"},
    },
)
@comment_rate_limit
async def create_comment(
    comment_data: CommentCreate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    moderation_service = ModerationService(db)
    moderation_result = moderation_service.check_content(comment_data.content)

    if moderation_result["is_flagged"]:
        reasons: list[str] = moderation_result["reasons"]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content flagged for moderation: {', '.join(reasons)}",
        )

    parent_count = sum(
        [1 for x in [comment_data.event_id, comment_data.service_id] if x is not None]
    )

    if parent_count != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify exactly one of: event_id, service_id",
        )

    if comment_data.event_id:
        result = await db.execute(
            select(Event).where(Event.id == comment_data.event_id, Event.is_active)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
            )

    if comment_data.service_id:
        result = await db.execute(
            select(Service).where(
                Service.id == comment_data.service_id, Service.is_active
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Service not found"
            )

    if comment_data.parent_id:
        result = await db.execute(
            select(Comment).where(Comment.id == comment_data.parent_id)
        )
        parent_comment = result.scalar_one_or_none()
        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found"
            )

        if comment_data.event_id and parent_comment.event_id != comment_data.event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reply must be on the same event",
            )
        if (
            comment_data.service_id
            and parent_comment.service_id != comment_data.service_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reply must be on the same service",
            )

    comment_dict = comment_data.model_dump()
    comment_dict["author_id"] = current_user.id

    db_comment = Comment(**comment_dict)
    db.add(db_comment)
    await db.commit()
    await db.refresh(db_comment, ["author", "replies"])

    if moderation_result["requires_review"]:
        background_tasks.add_task(_schedule_user_review, db, current_user.id)

    return CommentRead.model_validate(db_comment)


@router.put(
    "/{comment_id}",
    response_model=CommentRead,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid comment data or content flagged",
        },
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to edit this comment",
        },
        404: {"model": ErrorResponse, "description": "Comment not found"},
    },
)
async def update_comment(
    comment_id: int,
    comment_data: CommentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    moderation_service = ModerationService(db)
    moderation_result = moderation_service.check_content(comment_data.content)

    if moderation_result["is_flagged"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content flagged for moderation: {', '.join(moderation_result['reasons'])}",
        )

    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    if comment.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this comment",
        )

    comment.content = comment_data.content

    await db.commit()
    await db.refresh(comment, ["author", "replies"])

    return CommentRead.model_validate(comment)


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to delete this comment",
        },
        404: {"model": ErrorResponse, "description": "Comment not found"},
    },
)
async def delete_comment(
    comment_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    if comment.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment",
        )

    _ = await db.execute(delete(Comment).where(Comment.id == comment_id))
    await db.commit()


@router.get(
    "/my/",
    response_model=list[CommentRead],
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def get_my_comments(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    query = (
        select(Comment)
        .where(Comment.author_id == current_user.id)
        .options(selectinload(Comment.author), selectinload(Comment.replies))
        .order_by(Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    comments = result.scalars().all()

    return [CommentRead.model_validate(comment) for comment in comments]


@router.get(
    "/admin/moderation-queue",
    responses={403: {"model": ErrorResponse, "description": "Admin access required"}},
)
async def get_moderation_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    moderation_service = ModerationService(db)
    queue = await moderation_service.get_moderation_queue()

    return {"moderation_queue": queue}


@router.post(
    "/admin/moderate-user/{user_id}",
    responses={403: {"model": ErrorResponse, "description": "Admin access required"}},
)
async def moderate_user_content(
    user_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    moderation_service = ModerationService(db)
    analysis = await moderation_service.moderate_user_content(user_id)

    return analysis


async def _schedule_user_review(db: AsyncSession, user_id: int):
    moderation_service = ModerationService(db)
    user_analysis = await moderation_service.moderate_user_content(user_id)

    if user_analysis["needs_admin_review"]:
        print(
            f"🚨 User {user_id} needs admin review - Risk score: {user_analysis['average_risk_score']}"
        )
