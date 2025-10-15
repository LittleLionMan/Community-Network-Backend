from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from typing import Annotated
import re

from app.database import get_db
from app.models.forum import ForumThread, ForumPost, ForumCategory, ForumThreadView
from app.models.user import User
from app.models.achievement import UserAchievement
from app.schemas.forum import (
    ForumThreadCreate,
    ForumThreadRead,
    ForumThreadUpdate,
    ForumPostCreate,
    ForumPostRead,
    ForumPostUpdate,
)
from app.schemas.common import ErrorResponse
from app.core.dependencies import get_current_user, get_moderation_service
from app.core.rate_limit_decorator import (
    forum_post_rate_limit,
    forum_reply_rate_limit,
    read_rate_limit,
)
from app.services.moderation_service import ModerationService
from app.services.notification_service import NotificationService

router = APIRouter()


async def _enrich_posts_with_achievements(
    posts: list[ForumPost], db: AsyncSession, achievement_type: str
) -> None:
    post_ids = [post.id for post in posts]

    if not post_ids:
        return

    achievement_result = await db.execute(
        select(UserAchievement.reference_id, UserAchievement.achievement_type).where(
            UserAchievement.achievement_type == achievement_type,
            UserAchievement.reference_type == "forum_post",
            UserAchievement.reference_id.in_(post_ids),
        )
    )

    achievement_post_ids = set(achievement_result.scalars().all())

    for post in posts:
        post.has_achievement = post.id in achievement_post_ids


def extract_mentions(html_content: str) -> list[int]:
    pattern = r'data-id="(\d+)"'
    matches = re.findall(pattern, html_content)
    return [int(user_id) for user_id in matches if user_id.isdigit()]


@router.get(
    "/",
    response_model=list[ForumThreadRead],
    summary="Get all forum threads",
    description="Public endpoint to retrieve all threads with pagination",
)
@read_rate_limit("forum_listing")
async def get_threads(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    category_id: Annotated[int | None, Query(description="Filter by category")] = None,
    pinned_first: Annotated[
        bool, Query(description="Show pinned threads first")
    ] = True,
):
    query = select(ForumThread)

    if category_id:
        query = query.where(ForumThread.category_id == category_id)

    if pinned_first:
        query = query.order_by(
            ForumThread.is_pinned.desc(), ForumThread.created_at.desc()
        )
    else:
        query = query.order_by(ForumThread.created_at.desc())

    query = query.offset(skip).limit(limit)
    query = query.options(
        selectinload(ForumThread.creator), selectinload(ForumThread.category)
    )

    result = await db.execute(query)
    threads = result.scalars().all()
    enriched_threads: list[ForumThreadRead] = []
    for thread in threads:
        post_count_result = await db.execute(
            select(func.count(ForumPost.id)).where(ForumPost.thread_id == thread.id)
        )
        post_count = post_count_result.scalar() or 0

        latest_post_result = await db.execute(
            select(ForumPost.created_at)
            .where(ForumPost.thread_id == thread.id)
            .order_by(ForumPost.created_at.desc())
            .limit(1)
        )
        latest_post = latest_post_result.scalar_one_or_none()

        thread_dict = ForumThreadRead.model_validate(thread).model_dump()
        thread_dict["post_count"] = post_count
        thread_dict["latest_post"] = latest_post.isoformat() if latest_post else None

        enriched_threads.append(ForumThreadRead.model_validate(thread_dict))

    return enriched_threads


@router.get(
    "/category/{category_id}",
    response_model=list[ForumThreadRead],
    summary="Get threads in specific category",
)
async def get_threads_in_category(
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: int,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    pinned_first: Annotated[
        bool, Query(description="Show pinned threads first")
    ] = True,
):
    result = await db.execute(
        select(ForumCategory).where(ForumCategory.id == category_id)
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    query = select(ForumThread).where(ForumThread.category_id == category_id)

    if pinned_first:
        query = query.order_by(
            ForumThread.is_pinned.desc(), ForumThread.created_at.desc()
        )
    else:
        query = query.order_by(ForumThread.created_at.desc())

    query = query.offset(skip).limit(limit)
    query = query.options(
        selectinload(ForumThread.creator), selectinload(ForumThread.category)
    )

    result = await db.execute(query)
    threads = result.scalars().all()

    enriched_threads: list[ForumThreadRead] = []
    for thread in threads:
        post_count_result = await db.execute(
            select(func.count(ForumPost.id)).where(ForumPost.thread_id == thread.id)
        )
        post_count = post_count_result.scalar() or 0

        latest_post_result = await db.execute(
            select(ForumPost.created_at)
            .where(ForumPost.thread_id == thread.id)
            .order_by(ForumPost.created_at.desc())
            .limit(1)
        )
        latest_post = latest_post_result.scalar_one_or_none()

        thread_dict = ForumThreadRead.model_validate(thread).model_dump()
        thread_dict["post_count"] = post_count
        thread_dict["latest_post"] = latest_post.isoformat() if latest_post else None

        enriched_threads.append(ForumThreadRead.model_validate(thread_dict))

    return enriched_threads


@router.get("/my/threads", response_model=list[ForumThreadRead])
async def get_my_threads(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    query = (
        select(ForumThread)
        .where(ForumThread.creator_id == current_user.id)
        .options(selectinload(ForumThread.creator), selectinload(ForumThread.category))
        .order_by(ForumThread.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    threads = result.scalars().all()

    enriched_threads: list[ForumThreadRead] = []
    for thread in threads:
        post_count_result = await db.execute(
            select(func.count(ForumPost.id)).where(ForumPost.thread_id == thread.id)
        )
        post_count = post_count_result.scalar() or 0

        latest_post_result = await db.execute(
            select(ForumPost.created_at)
            .where(ForumPost.thread_id == thread.id)
            .order_by(ForumPost.created_at.desc())
            .limit(1)
        )
        latest_post = latest_post_result.scalar_one_or_none()

        thread_dict = ForumThreadRead.model_validate(thread).model_dump()
        thread_dict["post_count"] = post_count
        thread_dict["latest_post"] = latest_post.isoformat() if latest_post else None

        enriched_threads.append(ForumThreadRead.model_validate(thread_dict))

    return enriched_threads


@router.get("/my/posts", response_model=list[ForumPostRead])
async def get_my_posts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    check_achievement: Annotated[str | None, Query()] = None,
):
    query = (
        select(ForumPost)
        .where(ForumPost.author_id == current_user.id)
        .options(selectinload(ForumPost.author))
        .order_by(ForumPost.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    posts = result.scalars().all()
    posts_list = list(posts)

    if check_achievement:
        await _enrich_posts_with_achievements(posts_list, db, check_achievement)

    return [ForumPostRead.model_validate(post) for post in posts_list]


async def _check_user_moderation_status(
    user_id: int, moderation_service: ModerationService
):
    try:
        analysis = await moderation_service.moderate_user_content(user_id)

        if analysis["needs_admin_review"]:
            print(f"🚨 User {user_id} flagged for admin review:")
            print(f"   - Flagged items: {analysis['flagged_items']}")
            print(f"   - Risk score: {analysis['average_risk_score']:.2f}")

    except Exception as e:
        print(f"⚠️ Background moderation check failed for user {user_id}: {e}")


@router.get(
    "/unread-status",
    summary="Get unread status for multiple threads",
)
async def get_unread_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    thread_ids: Annotated[list[int], Query()] = [],
):
    if not thread_ids:
        return {}

    views_result = await db.execute(
        select(ForumThreadView).where(
            ForumThreadView.user_id == current_user.id,
            ForumThreadView.thread_id.in_(thread_ids),
        )
    )
    views = {
        view.thread_id: view.last_viewed_at for view in views_result.scalars().all()
    }

    latest_posts_result = await db.execute(
        select(ForumPost.thread_id, func.max(ForumPost.created_at).label("latest_post"))
        .where(ForumPost.thread_id.in_(thread_ids))
        .group_by(ForumPost.thread_id)
    )
    latest_posts = {
        thread_id: latest_post for thread_id, latest_post in latest_posts_result.all()
    }

    unread_status = {}
    for thread_id in thread_ids:
        last_viewed = views.get(thread_id)
        latest_post = latest_posts.get(thread_id)

        if last_viewed is None:
            unread_status[thread_id] = True
        elif latest_post is None:
            unread_status[thread_id] = False
        else:
            unread_status[thread_id] = latest_post > last_viewed

    return unread_status


@router.get(
    "/{thread_id}",
    response_model=ForumThreadRead,
    responses={404: {"model": ErrorResponse, "description": "Thread not found"}},
)
async def get_thread(thread_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    query = (
        select(ForumThread)
        .where(ForumThread.id == thread_id)
        .options(selectinload(ForumThread.creator), selectinload(ForumThread.category))
    )

    result = await db.execute(query)
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    post_count_result = await db.execute(
        select(func.count(ForumPost.id)).where(ForumPost.thread_id == thread.id)
    )
    post_count = post_count_result.scalar() or 0

    latest_post_result = await db.execute(
        select(ForumPost.created_at)
        .where(ForumPost.thread_id == thread.id)
        .order_by(ForumPost.created_at.desc())
        .limit(1)
    )
    latest_post = latest_post_result.scalar_one_or_none()

    thread_dict = ForumThreadRead.model_validate(thread).model_dump()
    thread_dict["post_count"] = post_count
    thread_dict["latest_post"] = latest_post.isoformat() if latest_post else None

    return ForumThreadRead.model_validate(thread_dict)


@router.post(
    "/",
    response_model=ForumThreadRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid thread data or title flagged",
        },
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Category not found"},
    },
)
@forum_post_rate_limit
async def create_thread(
    thread_data: ForumThreadCreate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    moderation_service: Annotated[ModerationService, Depends(get_moderation_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(ForumCategory).where(
            ForumCategory.id == thread_data.category_id, ForumCategory.is_active
        )
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found or inactive",
        )

    moderation_result = moderation_service.check_content(thread_data.title)

    if moderation_result["is_flagged"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Thread title flagged: {', '.join(moderation_result['reasons'])}",
        )

    thread_dict = thread_data.model_dump()
    thread_dict["creator_id"] = current_user.id

    db_thread = ForumThread(**thread_dict)
    db.add(db_thread)
    await db.commit()
    await db.refresh(db_thread, ["creator", "category"])

    if moderation_result["requires_review"]:
        background_tasks.add_task(
            _check_user_moderation_status, current_user.id, moderation_service
        )

    return ForumThreadRead.model_validate(db_thread)


@router.put(
    "/{thread_id}",
    response_model=ForumThreadRead,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid thread data"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to edit this thread",
        },
        404: {"model": ErrorResponse, "description": "Thread not found"},
    },
)
async def update_thread(
    thread_id: int,
    thread_data: ForumThreadUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(ForumThread).where(ForumThread.id == thread_id))
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    if thread.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this thread",
        )

    if not current_user.is_admin:
        if thread_data.is_pinned is not None or thread_data.is_locked is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can pin/lock threads",
            )

    if thread_data.category_id and thread_data.category_id != thread.category_id:
        result = await db.execute(
            select(ForumCategory).where(
                ForumCategory.id == thread_data.category_id, ForumCategory.is_active
            )
        )
        category = result.scalar_one_or_none()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="New category not found or inactive",
            )

    update_data: dict[str, object] = thread_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(thread, field, value)

    await db.commit()
    await db.refresh(thread, ["creator", "category"])

    return ForumThreadRead.model_validate(thread)


@router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to delete this thread",
        },
        404: {"model": ErrorResponse, "description": "Thread not found"},
    },
)
async def delete_thread(
    thread_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(ForumThread).where(ForumThread.id == thread_id))
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    if thread.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this thread",
        )

    _ = await db.execute(delete(ForumThread).where(ForumThread.id == thread_id))
    await db.commit()


@router.get(
    "/{thread_id}/posts",
    response_model=list[ForumPostRead],
    responses={404: {"model": ErrorResponse, "description": "Thread not found"}},
)
async def get_thread_posts(
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    check_achievement: Annotated[str | None, Query()] = None,
):
    result = await db.execute(select(ForumThread).where(ForumThread.id == thread_id))
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    all_posts_query = (
        select(ForumPost)
        .where(ForumPost.thread_id == thread_id)
        .options(selectinload(ForumPost.author))
        .order_by(ForumPost.created_at.desc())
        .limit(500)
    )

    all_posts_result = await db.execute(all_posts_query)
    all_posts = list(all_posts_result.scalars().all())
    all_posts.reverse()

    posts_map = {post.id: post for post in all_posts}

    def build_quoted_chain(post, depth=0, visited=None):
        if visited is None:
            visited = set()

        if post.id in visited or depth > 50:
            return

        visited.add(post.id)

        if post.quoted_post_id:
            if post.quoted_post_id in posts_map:
                quoted = posts_map[post.quoted_post_id]
                post.quoted_post = quoted
                build_quoted_chain(quoted, depth + 1, visited)
            else:
                deleted_post = type(
                    "obj",
                    (object,),
                    {
                        "id": post.quoted_post_id,
                        "content": "<p><em>[Zitierter Post nicht verfügbar - möglicherweise gelöscht oder zu alt]</em></p>",
                        "created_at": post.created_at,
                        "author": type(
                            "obj",
                            (object,),
                            {
                                "id": 0,
                                "display_name": "[Gelöscht]",
                                "profile_image_url": None,
                            },
                        )(),
                        "thread_id": thread_id,
                        "quoted_post": None,
                    },
                )()
                post.quoted_post = deleted_post

    for post in all_posts:
        build_quoted_chain(post)

    paginated_posts = all_posts[skip : skip + limit]
    if check_achievement:
        await _enrich_posts_with_achievements(paginated_posts, db, check_achievement)

    return [ForumPostRead.model_validate(post) for post in paginated_posts]


@router.post(
    "/{thread_id}/posts",
    response_model=ForumPostRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Thread is locked, invalid data, or content flagged",
        },
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Thread not found"},
    },
)
@forum_reply_rate_limit
async def create_post(
    thread_id: int,
    post_data: ForumPostCreate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    moderation_service: Annotated[ModerationService, Depends(get_moderation_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    moderation_result = moderation_service.check_content(post_data.content)

    if moderation_result["is_flagged"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Post content flagged: {', '.join(moderation_result['reasons'])}",
        )

    result = await db.execute(
        select(ForumThread)
        .options(selectinload(ForumThread.creator))
        .where(ForumThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )

    if thread.is_locked and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Thread is locked"
        )

    quoted_post = None
    if post_data.quoted_post_id:
        result = await db.execute(
            select(ForumPost)
            .options(selectinload(ForumPost.author))
            .where(
                ForumPost.id == post_data.quoted_post_id,
                ForumPost.thread_id == thread_id,
            )
        )
        quoted_post = result.scalar_one_or_none()

        if not quoted_post:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quoted post not found or not in this thread",
            )

    mentioned_user_ids = extract_mentions(post_data.content)

    post_dict = post_data.model_dump()
    post_dict["thread_id"] = thread_id
    post_dict["author_id"] = current_user.id
    post_dict["mentioned_user_ids"] = mentioned_user_ids if mentioned_user_ids else None

    db_post = ForumPost(**post_dict)
    db.add(db_post)
    await db.flush()
    await db.refresh(db_post, ["author"])

    notification_service = NotificationService()

    if thread.creator_id != current_user.id:
        _ = await notification_service.create_forum_reply_notification(
            db, thread, db_post, current_user
        )

    if mentioned_user_ids:
        _ = await notification_service.create_forum_mention_notifications(
            db, thread, db_post, mentioned_user_ids, current_user
        )

    if quoted_post and quoted_post.author_id != current_user.id:
        _ = await notification_service.create_forum_quote_notification(
            db, thread, db_post, quoted_post, current_user
        )

    await db.commit()
    await db.refresh(db_post, ["author", "quoted_post"])

    if moderation_result["requires_review"]:
        background_tasks.add_task(
            _check_user_moderation_status, current_user.id, moderation_service
        )

    return ForumPostRead.model_validate(db_post)


@router.put("/posts/{post_id}", response_model=ForumPostRead)
async def update_post(
    post_id: int,
    post_data: ForumPostUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(ForumPost).where(ForumPost.id == post_id))
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    if post.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this post",
        )

    post.content = post_data.content
    from datetime import datetime

    post.updated_at = datetime.now()

    await db.commit()
    await db.refresh(post, ["author"])

    return ForumPostRead.model_validate(post)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(ForumPost).where(ForumPost.id == post_id))
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    if post.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post",
        )

    _ = await db.execute(delete(ForumPost).where(ForumPost.id == post_id))
    await db.commit()


@router.get("/admin/flagged-content")
async def get_flagged_content(
    moderation_service: Annotated[ModerationService, Depends(get_moderation_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    recent_posts = await db.execute(
        select(ForumPost)
        .options(selectinload(ForumPost.author))
        .order_by(ForumPost.created_at.desc())
        .limit(100)
    )
    posts = recent_posts.scalars().all()

    flagged_posts = []
    for post in posts:
        moderation_result = moderation_service.check_content(post.content)
        if moderation_result["requires_review"]:
            flagged_posts.append(
                {
                    "post_id": post.id,
                    "thread_id": post.thread_id,
                    "author": post.author.display_name,
                    "content_preview": post.content[:200] + "..."
                    if len(post.content) > 200
                    else post.content,
                    "created_at": post.created_at,
                    "moderation": moderation_result,
                }
            )

    flagged_posts.sort(
        key=lambda x: x["moderation"]["confidence"],  # type: ignore[arg-type]
        reverse=True,
    )

    return {"flagged_posts": flagged_posts[:limit], "total_flagged": len(flagged_posts)}


@router.post(
    "/{thread_id}/mark-read",
    summary="Mark thread as read",
)
async def mark_thread_as_read(
    thread_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(ForumThread).where(ForumThread.id == thread_id))
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )
    try:
        stmt = pg_insert(ForumThreadView).values(
            user_id=current_user.id, thread_id=thread_id, last_viewed_at=func.now()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "thread_id"], set_={"last_viewed_at": func.now()}
        )
    except:
        stmt = mysql_insert(ForumThreadView).values(
            user_id=current_user.id, thread_id=thread_id, last_viewed_at=func.now()
        )
        stmt = stmt.on_duplicate_key_update(last_viewed_at=func.now())

    _ = await db.execute(stmt)
    await db.commit()

    return {"message": "Thread marked as read"}
