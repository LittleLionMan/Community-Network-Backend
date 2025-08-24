from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.forum import ForumThread, ForumPost
from app.models.user import User
from app.schemas.forum import (
    ForumThreadCreate, ForumThreadRead, ForumThreadUpdate,
    ForumPostCreate, ForumPostRead, ForumPostUpdate
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_current_admin_user, get_optional_current_user, get_moderation_service
from app.services.moderation_service import ModerationService

router = APIRouter()

@router.get(
    "/",
    response_model=List[ForumThreadRead],
    summary="Get all forum threads",
    description="Public endpoint to retrieve all threads with pagination"
)
async def get_threads(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    pinned_first: bool = Query(True, description="Show pinned threads first"),
    db: AsyncSession = Depends(get_db)
):
    query = select(ForumThread)

    if pinned_first:
        query = query.order_by(
            ForumThread.is_pinned.desc(),
            ForumThread.created_at.desc()
        )
    else:
        query = query.order_by(ForumThread.created_at.desc())

    query = query.offset(skip).limit(limit)

    query = query.options(selectinload(ForumThread.creator))

    result = await db.execute(query)
    threads = result.scalars().all()

    return [ForumThreadRead.model_validate(thread) for thread in threads]

@router.get(
    "/{thread_id}",
    response_model=ForumThreadRead,
    responses={
        404: {"model": ErrorResponse, "description": "Thread not found"}
    }
)
async def get_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db)
):
    query = select(ForumThread).where(
        ForumThread.id == thread_id
    ).options(selectinload(ForumThread.creator))

    result = await db.execute(query)
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    return ForumThreadRead.model_validate(thread)

@router.post(
    "/",
    response_model=ForumThreadRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid thread data or title flagged"},
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def create_thread(
    thread_data: ForumThreadCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    moderation_service: ModerationService = Depends(get_moderation_service),
    db: AsyncSession = Depends(get_db)
):
    moderation_result = moderation_service.check_content(thread_data.title)

    if moderation_result['is_flagged']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Thread title flagged: {', '.join(moderation_result['reasons'])}"
        )

    thread_dict = thread_data.model_dump()
    thread_dict["creator_id"] = current_user.id

    db_thread = ForumThread(**thread_dict)
    db.add(db_thread)
    await db.commit()
    await db.refresh(db_thread, ["creator"])

    if moderation_result['requires_review']:
        background_tasks.add_task(
            _check_user_moderation_status,
            db,
            current_user.id,
            moderation_service
        )

    return ForumThreadRead.model_validate(db_thread)

@router.put(
    "/{thread_id}",
    response_model=ForumThreadRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid thread data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this thread"},
        404: {"model": ErrorResponse, "description": "Thread not found"}
    }
)
async def update_thread(
    thread_id: int,
    thread_data: ForumThreadUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumThread).where(ForumThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    if thread.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this thread"
        )

    if not current_user.is_admin:
        if thread_data.is_pinned is not None or thread_data.is_locked is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can pin/lock threads"
            )

    update_data = thread_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(thread, field, value)

    await db.commit()
    await db.refresh(thread, ["creator"])

    return ForumThreadRead.model_validate(thread)

@router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to delete this thread"},
        404: {"model": ErrorResponse, "description": "Thread not found"}
    }
)
async def delete_thread(
    thread_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumThread).where(ForumThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    if thread.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this thread"
        )

    await db.execute(
        delete(ForumThread).where(ForumThread.id == thread_id)
    )
    await db.commit()

@router.get(
    "/{thread_id}/posts",
    response_model=List[ForumPostRead],
    responses={
        404: {"model": ErrorResponse, "description": "Thread not found"}
    }
)
async def get_thread_posts(
    thread_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumThread).where(ForumThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    query = select(ForumPost).where(
        ForumPost.thread_id == thread_id
    ).options(
        selectinload(ForumPost.author)
    ).order_by(ForumPost.created_at.asc()).offset(skip).limit(limit)

    result = await db.execute(query)
    posts = result.scalars().all()

    return [ForumPostRead.model_validate(post) for post in posts]

@router.post(
    "/{thread_id}/posts",
    response_model=ForumPostRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Thread is locked, invalid data, or content flagged"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Thread not found"}
    }
)
async def create_post(
    thread_id: int,
    post_data: ForumPostCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    moderation_service: ModerationService = Depends(get_moderation_service),
    db: AsyncSession = Depends(get_db)
):
    moderation_result = moderation_service.check_content(post_data.content)

    if moderation_result['is_flagged']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Post content flagged: {', '.join(moderation_result['reasons'])}"
        )

    result = await db.execute(
        select(ForumThread).where(ForumThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    if thread.is_locked and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thread is locked"
        )

    post_dict = post_data.model_dump()
    post_dict["thread_id"] = thread_id
    post_dict["author_id"] = current_user.id

    db_post = ForumPost(**post_dict)
    db.add(db_post)
    await db.commit()
    await db.refresh(db_post, ["author"])

    if moderation_result['requires_review']:
        background_tasks.add_task(
            _check_user_moderation_status,
            db,
            current_user.id,
            moderation_service
        )

    return ForumPostRead.model_validate(db_post)

@router.put(
    "/posts/{post_id}",
    response_model=ForumPostRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid post data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to edit this post"},
        404: {"model": ErrorResponse, "description": "Post not found"}
    }
)
async def update_post(
    post_id: int,
    post_data: ForumPostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumPost).where(ForumPost.id == post_id)
    )
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    if post.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this post"
        )

    post.content = post_data.content
    from datetime import datetime
    post.updated_at = datetime.now()

    await db.commit()
    await db.refresh(post, ["author"])

    return ForumPostRead.model_validate(post)

@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Not authorized to delete this post"},
        404: {"model": ErrorResponse, "description": "Post not found"}
    }
)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ForumPost).where(ForumPost.id == post_id)
    )
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    if post.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post"
        )

    await db.execute(
        delete(ForumPost).where(ForumPost.id == post_id)
    )
    await db.commit()

@router.get(
    "/my/threads",
    response_model=List[ForumThreadRead],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_threads(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(ForumThread).where(
        ForumThread.creator_id == current_user.id
    ).options(
        selectinload(ForumThread.creator)
    ).order_by(ForumThread.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    threads = result.scalars().all()

    return [ForumThreadRead.model_validate(thread) for thread in threads]

@router.get(
    "/my/posts",
    response_model=List[ForumPostRead],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_my_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(ForumPost).where(
        ForumPost.author_id == current_user.id
    ).options(
        selectinload(ForumPost.author)
    ).order_by(ForumPost.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    posts = result.scalars().all()

    return [ForumPostRead.model_validate(post) for post in posts]

async def _check_user_moderation_status(
    db: AsyncSession,
    user_id: int,
    moderation_service: ModerationService
):

    try:
        analysis = await moderation_service.moderate_user_content(user_id)

        if analysis['needs_admin_review']:
            print(f"🚨 User {user_id} flagged for admin review:")
            print(f"   - Flagged items: {analysis['flagged_items']}")
            print(f"   - Risk score: {analysis['average_risk_score']:.2f}")

            # In production, you'd:
            # 1. Add to moderation queue table
            # 2. Send notification to admins
            # 3. Potentially auto-suspend user if score is very high
    except Exception as e:
        print(f"⚠️ Background moderation check failed for user {user_id}: {e}")

@router.get(
    "/admin/flagged-content",
    responses={
        403: {"model": ErrorResponse, "description": "Admin access required"}
    }
)
async def get_flagged_content(
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin_user),
    moderation_service: ModerationService = Depends(get_moderation_service),
    db: AsyncSession = Depends(get_db)
):
    recent_posts = await db.execute(
        select(ForumPost).options(selectinload(ForumPost.author))
        .order_by(ForumPost.created_at.desc()).limit(100)
    )
    posts = recent_posts.scalars().all()

    flagged_posts = []
    for post in posts:
        moderation_result = moderation_service.check_content(post.content)
        if moderation_result['requires_review']:
            flagged_posts.append({
                'post_id': post.id,
                'thread_id': post.thread_id,
                'author': post.author.display_name,
                'content_preview': post.content[:200] + "..." if len(post.content) > 200 else post.content,
                'created_at': post.created_at,
                'moderation': moderation_result
            })

    flagged_posts.sort(key=lambda x: x['moderation']['confidence'], reverse=True)

    return {
        'flagged_posts': flagged_posts[:limit],
        'total_flagged': len(flagged_posts)
    }
