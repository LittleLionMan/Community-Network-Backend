from fastapi import FastAPI, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from app.config import settings
from app.api import auth, users, event_categories, events, services, discussions, comments, polls, forum_categories

from app.database import get_db
from app.core.dependencies import get_current_admin_user
from app.services.scheduler_service import scheduler_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = structlog.get_logger()
    logger.info("Community Platform API starting up")

    try:
        if settings.DEBUG:
            logger.info("Running in debug mode - enhanced logging enabled")

        scheduler_service.start()
        logger.info("Business logic services initialized")

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    logger.info("Community Platform API shutting down")
    scheduler_service.stop()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(event_categories.router, prefix="/api/event-categories", tags=["event-categories"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(discussions.router, prefix="/api/discussions", tags=["discussions"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(polls.router, prefix="/api/polls", tags=["polls"])
app.include_router(forum_categories.router, prefix="/api/forum-categories", tags=["forum-categories"])

@app.get("/health")
async def health_check(request: Request):

    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "timestamp": datetime.now().isoformat(),
        "features": {
            "authentication": True,
            "events": True,
            "services": True,
            "forum": True,
            "polling": True,
            "content_moderation": settings.CONTENT_MODERATION_ENABLED,
            "service_matching": getattr(settings, 'SERVICE_MATCHING_ENABLED', True),
            "auto_attendance": getattr(settings, 'EVENT_AUTO_ATTENDANCE_ENABLED', True)
        }
    }

    return health_status

@app.get("/api/admin/dashboard")
async def admin_dashboard(
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    from app.models.user import User
    from app.models.event import Event
    from app.models.service import Service
    from app.models.comment import Comment
    from app.models.forum import ForumPost, ForumThread
    from app.models.poll import Poll, Vote

    stats = {}

    try:
        user_count = await db.execute(select(func.count(User.id)).where(User.is_active == True))
        stats['total_users'] = user_count.scalar() or 0

        event_count = await db.execute(select(func.count(Event.id)).where(Event.is_active == True))
        stats['total_events'] = event_count.scalar() or 0

        service_count = await db.execute(select(func.count(Service.id)).where(Service.is_active == True))
        stats['total_services'] = service_count.scalar() or 0

        comment_count = await db.execute(select(func.count(Comment.id)))
        forum_posts_count = await db.execute(select(func.count(ForumPost.id)))
        stats['total_comments'] = comment_count.scalar() or 0
        stats['total_forum_posts'] = forum_posts_count.scalar() or 0

        poll_count = await db.execute(select(func.count(Poll.id)))
        vote_count = await db.execute(select(func.count(Vote.id)))
        stats['total_polls'] = poll_count.scalar() or 0
        stats['total_votes'] = vote_count.scalar() or 0

        week_ago = datetime.now() - timedelta(days=7)

        recent_users = await db.execute(
            select(func.count(User.id)).where(User.created_at > week_ago)
        )
        recent_events = await db.execute(
            select(func.count(Event.id)).where(Event.created_at > week_ago)
        )
        recent_services = await db.execute(
            select(func.count(Service.id)).where(Service.created_at > week_ago)
        )

        stats['recent_activity'] = {
            'new_users_7d': recent_users.scalar() or 0,
            'new_events_7d': recent_events.scalar() or 0,
            'new_services_7d': recent_services.scalar() or 0
        }

    except Exception as e:
        stats = {
            'total_users': 0,
            'total_events': 0,
            'total_services': 0,
            'total_comments': 0,
            'total_forum_posts': 0,
            'total_polls': 0,
            'total_votes': 0,
            'recent_activity': {
                'new_users_7d': 0,
                'new_events_7d': 0,
                'new_services_7d': 0
            },
            'error': str(e)
        }

    return {
        'platform_stats': stats,
        'health': {
            'database': 'connected',
            'moderation': 'active' if settings.CONTENT_MODERATION_ENABLED else 'disabled',
            'matching': 'active' if getattr(settings, 'SERVICE_MATCHING_ENABLED', True) else 'disabled'
        },
        'settings': {
            'debug_mode': settings.DEBUG,
            'content_moderation_enabled': settings.CONTENT_MODERATION_ENABLED,
            'moderation_threshold': getattr(settings, 'MODERATION_THRESHOLD', 0.7),
            'service_matching_enabled': getattr(settings, 'SERVICE_MATCHING_ENABLED', True),
            'event_auto_attendance': getattr(settings, 'EVENT_AUTO_ATTENDANCE_ENABLED', True)
        }
    }

@app.post("/api/admin/tasks/process-events")
async def process_completed_events(
    background_tasks: BackgroundTasks,
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):

    from app.services.event_service import EventService
    from app.models.event import Event

    try:
        cutoff_time = datetime.now() - timedelta(hours=1)

        result = await db.execute(
            select(Event).where(
                Event.end_datetime < cutoff_time,
                Event.is_active == True
            )
        )
        events = result.scalars().all()

        event_service = EventService(db)
        for event in events:
            background_tasks.add_task(event_service.auto_mark_attendance, event.id)

        return {
            "message": f"Scheduled processing for {len(events)} completed events",
            "events_processed": len(events)
        }
    except Exception as e:
        return {
            "message": "Failed to process events",
            "error": str(e),
            "events_processed": 0
        }

@app.get("/api/stats")
async def public_platform_stats(db: AsyncSession = Depends(get_db)):

    from sqlalchemy import func, select
    from app.models.user import User
    from app.models.event import Event
    from app.models.service import Service
    from app.models.poll import Poll

    try:
        user_count = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )

        active_events = await db.execute(
            select(func.count(Event.id)).where(
                Event.is_active == True,
                Event.start_datetime > datetime.now()
            )
        )

        active_services = await db.execute(
            select(func.count(Service.id)).where(Service.is_active == True)
        )

        active_polls = await db.execute(
            select(func.count(Poll.id)).where(Poll.is_active == True)
        )

        return {
            "community_size": user_count.scalar() or 0,
            "upcoming_events": active_events.scalar() or 0,
            "active_services": active_services.scalar() or 0,
            "active_polls": active_polls.scalar() or 0,
            "platform_version": settings.VERSION
        }
    except Exception as e:
        return {
            "community_size": 0,
            "upcoming_events": 0,
            "active_services": 0,
            "active_polls": 0,
            "platform_version": settings.VERSION,
            "error": "Stats temporarily unavailable"
        }

@app.post("/api/admin/tasks/trigger-cleanup")
async def trigger_cleanup(
    current_admin = Depends(get_current_admin_user)
):
    """Manual trigger for cleanup tasks"""
    try:
        await scheduler_service.daily_cleanup()
        return {"message": "Cleanup triggered successfully"}
    except Exception as e:
        return {"message": f"Cleanup failed: {str(e)}"}
