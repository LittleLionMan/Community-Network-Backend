from fastapi import FastAPI, Request, BackgroundTasks, Depends
from typing import Annotated, cast
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text
from dotenv import load_dotenv
from pathlib import Path
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

env_path = Path(__file__).resolve().parent.parent / ".env"
_ = load_dotenv(dotenv_path=env_path)

from app.config import settings
from app.database import get_db
from app.core.dependencies import get_current_admin_user
from app.services.scheduler_service import scheduler_service
from app.core.logging import SecurityLogger
from app.core.monitoring import rate_limit_monitor
from app.core.middleware import setup_middleware
from app.core.telegram import notify_telegram, TelegramNotifier
from app.core.background_tasks import (
    startup_background_tasks,
    shutdown_background_tasks,
    run_maintenance,
)
from app.services.event_service import EventService
from app.api import (
    auth,
    users,
    event_categories,
    events,
    services,
    discussions,
    comments,
    polls,
    forum_categories,
    messages,
    admin_security,
    admin_rate_limits,
    notifications,
    achievements,
)
from app.models.user import User
from app.models.event import Event
from app.models.service import Service
from app.models.poll import Poll
from app.models.comment import Comment
from app.models.forum import ForumPost
from app.models.poll import Poll, Vote
from app.models.message import Message, Conversation
from app.models.auth import RefreshToken

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("🚀 Community Platform API starting up")

    try:
        if settings.DEBUG:
            logger.info("Running in debug mode - enhanced logging enabled")

        scheduler_service.start()
        logger.info("✅ Business logic services initialized")

        await startup_background_tasks()
        logger.info("✅ Background tasks started (token rotation enabled)")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise

    yield

    logger.info("🛑 Community Platform API shutting down")

    try:
        scheduler_service.stop()

        await shutdown_background_tasks()
        logger.info("✅ All services stopped gracefully")
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")


if settings.SENTRY_DSN:
    _ = sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=1.0 if settings.DEBUG else 0.1,
        profiles_sample_rate=1.0 if settings.DEBUG else 0.1,
        environment=settings.ENVIRONMENT,
        release=f"community-platform@{settings.VERSION}",
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        ignore_errors=[
            KeyboardInterrupt,
        ],
        send_default_pii=False,
        enable_tracing=True,
        attach_stacktrace=True,
    )

    logger.info(f"✅ Sentry initialized for environment: {settings.ENVIRONMENT}")
else:
    logger.info("⚠️  Sentry DSN not configured - error tracking disabled")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

setup_middleware(app)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["plaetzchen.xyz", "www.plaetzchen.xyz", "localhost"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(
    event_categories.router, prefix="/api/event-categories", tags=["event-categories"]
)
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(discussions.router, prefix="/api/discussions", tags=["discussions"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(polls.router, prefix="/api/polls", tags=["polls"])
app.include_router(
    forum_categories.router, prefix="/api/forum-categories", tags=["forum-categories"]
)
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(admin_security.router, prefix="/api", tags=["admin-security"])
app.include_router(admin_rate_limits.router, prefix="/api")
app.include_router(
    notifications.router, prefix="/api/notifications", tags=["notifications"]
)
app.include_router(achievements.router, prefix="/api", tags=["achievements"])


@app.get("/health")
async def health_check():
    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {
            "authentication": True,
            "refresh_token_rotation": True,
            "structured_logging": True,
            "rate_limiting": True,
            "failed_login_protection": True,
            "events": True,
            "services": True,
            "forum": True,
            "polling": True,
            "messages": True,
            "content_moderation": settings.CONTENT_MODERATION_ENABLED,
            "service_matching": getattr(settings, "SERVICE_MATCHING_ENABLED", True),
            "auto_attendance": getattr(settings, "EVENT_AUTO_ATTENDANCE_ENABLED", True),
            "websocket_messaging": True,
            "background_tasks": True,
            "token_cleanup": True,
            "request_monitoring": True,
        },
    }

    return health_status


@app.get("/api/auth/token-status")
async def token_rotation_status():
    return {
        "token_rotation_enabled": True,
        "refresh_token_rotation": True,
        "background_cleanup": True,
        "security_features": [
            "refresh_token_rotation",
            "automatic_token_cleanup",
            "concurrent_refresh_protection",
            "replay_attack_prevention",
            "structured_security_logging",
        ],
    }


@app.get("/api/admin/rate-limiting/health")
async def get_rate_limiting_health(
    request: Request, current_admin: Annotated[User, Depends(get_current_admin_user)]
):
    SecurityLogger.log_admin_action(
        request, admin_user_id=current_admin.id, action="view_rate_limiting_health"
    )

    health_report = rate_limit_monitor.check_rate_limit_health()

    recent_alerts = rate_limit_monitor.get_recent_alerts(hours=24)

    return {
        "health": health_report,
        "recent_alerts": recent_alerts,
        "monitoring_active": True,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/admin/dashboard")
async def admin_dashboard(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    SecurityLogger.log_admin_action(
        request, admin_user_id=current_admin.id, action="dashboard_access"
    )

    stats: dict[str, object] = {}

    try:
        user_count = await db.execute(select(func.count(User.id)).where(User.is_active))
        stats["total_users"] = user_count.scalar() or 0

        event_count = await db.execute(
            select(func.count(Event.id)).where(Event.is_active)
        )
        stats["total_events"] = event_count.scalar() or 0

        service_count = await db.execute(
            select(func.count(Service.id)).where(Service.is_active)
        )
        stats["total_services"] = service_count.scalar() or 0

        comment_count = await db.execute(select(func.count(Comment.id)))
        forum_posts_count = await db.execute(select(func.count(ForumPost.id)))
        stats["total_comments"] = comment_count.scalar() or 0
        stats["total_forum_posts"] = forum_posts_count.scalar() or 0

        poll_count = await db.execute(select(func.count(Poll.id)))
        vote_count = await db.execute(select(func.count(Vote.id)))
        stats["total_polls"] = poll_count.scalar() or 0
        stats["total_votes"] = vote_count.scalar() or 0

        message_count = await db.execute(select(func.count(Message.id)))
        conversation_count = await db.execute(select(func.count(Conversation.id)))
        active_conversations = await db.execute(
            select(func.count(Conversation.id)).where(Conversation.is_active)
        )
        flagged_messages = await db.execute(
            select(func.count(Message.id)).where(Message.is_flagged)
        )

        stats["total_messages"] = message_count.scalar() or 0
        stats["total_conversations"] = conversation_count.scalar() or 0
        stats["active_conversations"] = active_conversations.scalar() or 0
        stats["flagged_messages"] = flagged_messages.scalar() or 0

        active_tokens = await db.execute(
            select(func.count(RefreshToken.id)).where(RefreshToken.is_revoked)
        )
        total_tokens = await db.execute(select(func.count(RefreshToken.id)))

        stats["active_refresh_tokens"] = active_tokens.scalar() or 0
        stats["total_refresh_tokens"] = total_tokens.scalar() or 0

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        recent_users = await db.execute(
            select(func.count(User.id)).where(User.created_at > week_ago)
        )
        recent_events = await db.execute(
            select(func.count(Event.id)).where(Event.created_at > week_ago)
        )
        recent_services = await db.execute(
            select(func.count(Service.id)).where(Service.created_at > week_ago)
        )

        stats["recent_activity"] = {
            "new_users_7d": recent_users.scalar() or 0,
            "new_events_7d": recent_events.scalar() or 0,
            "new_services_7d": recent_services.scalar() or 0,
        }

    except Exception as e:
        stats = {
            "total_users": 0,
            "total_events": 0,
            "total_services": 0,
            "total_comments": 0,
            "total_forum_posts": 0,
            "total_polls": 0,
            "total_votes": 0,
            "total_messages": 0,
            "active_refresh_tokens": 0,
            "total_refresh_tokens": 0,
            "recent_activity": {
                "new_users_7d": 0,
                "new_events_7d": 0,
                "new_services_7d": 0,
                "new_messages_7d": 0,
            },
            "error": str(e),
        }

    try:
        rate_limit_health = rate_limit_monitor.check_rate_limit_health()

        content_rate_limits = rate_limit_health.get("content_rate_limits", {})
        if isinstance(content_rate_limits, dict):
            safe_content_limits = cast(dict[str, object], content_rate_limits)
            stats["rate_limiting"] = {
                "health_score": rate_limit_health.get("health_score", 0),
                "status": rate_limit_health.get("status", "unknown"),
                "active_users": safe_content_limits.get("active_users", 0),
                "total_lockouts": safe_content_limits.get("total_lockouts", 0),
                "monitoring_enabled": True,
            }
        else:
            stats["rate_limiting"] = {
                "health_score": 0,
                "status": "error",
                "monitoring_enabled": False,
                "error": "Invalid rate limit data structure",
            }

    except Exception as e:
        stats["rate_limiting"] = {
            "health_score": 0,
            "status": "error",
            "monitoring_enabled": False,
            "error": str(e),
        }

    stats["security_monitoring"] = {
        "structured_logging": True,
        "rate_limiting": True,
        "monitoring_active": True,
        "note": "Security events now tracked via structured logging",
    }

    from app.services.websocket_service import websocket_manager

    ws_stats = websocket_manager.get_connection_stats()

    return {
        "platform_stats": stats,
        "websocket_stats": ws_stats,
        "health": {
            "database": "connected",
            "moderation": "active"
            if settings.CONTENT_MODERATION_ENABLED
            else "disabled",
            "matching": "active"
            if getattr(settings, "SERVICE_MATCHING_ENABLED", True)
            else "disabled",
            "messaging": "active",
            "websockets": "active",
            "token_rotation": "active",
            "structured_logging": True,
            "rate_limiting": True,
            "failed_login_protection": True,
            "request_monitoring": True,
        },
        "settings": {
            "debug_mode": settings.DEBUG,
            "content_moderation_enabled": settings.CONTENT_MODERATION_ENABLED,
            "moderation_threshold": getattr(settings, "MODERATION_THRESHOLD", 0.7),
            "service_matching_enabled": getattr(
                settings, "SERVICE_MATCHING_ENABLED", True
            ),
            "event_auto_attendance": getattr(
                settings, "EVENT_AUTO_ATTENDANCE_ENABLED", True
            ),
            "message_system_enabled": True,
            "refresh_token_rotation": True,
            "structured_logging": True,
        },
    }


@app.post("/api/admin/maintenance/tokens")
async def trigger_token_maintenance(
    request: Request, current_admin: Annotated[User, Depends(get_current_admin_user)]
):
    try:
        SecurityLogger.log_admin_action(
            request, admin_user_id=current_admin.id, action="trigger_token_maintenance"
        )

        await run_maintenance()
        return {
            "status": "success",
            "message": "Token maintenance completed successfully",
        }
    except Exception as e:
        logger.error(f"Manual token maintenance failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Token maintenance failed",
                "error": str(e),
            },
        )


@app.post("/api/admin/tasks/process-events")
async def process_completed_events(
    request: Request,
    background_tasks: BackgroundTasks,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        SecurityLogger.log_admin_action(
            request, admin_user_id=current_admin.id, action="process_completed_events"
        )

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)

        result = await db.execute(
            text("""
                SELECT * FROM events
                WHERE end_datetime IS NOT NULL
                AND end_datetime < :cutoff_time
                AND is_active = true
            """),
            {"cutoff_time": cutoff_time},
        )
        events = cast(list[Event], result.scalars().all())

        event_service = EventService(db)
        for event in events:
            background_tasks.add_task(event_service.auto_mark_attendance, event.id)

        return {
            "message": f"Scheduled processing for {len(events)} completed events",
            "events_processed": len(events),
        }
    except Exception as e:
        return {
            "message": "Failed to process events",
            "error": str(e),
            "events_processed": 0,
        }


@app.post("/api/admin/tasks/cleanup-messages")
async def cleanup_message_system(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.services.message_service import MessageService

    try:
        SecurityLogger.log_admin_action(
            request, admin_user_id=current_admin.id, action="cleanup_message_system"
        )

        message_service = MessageService(db)

        old_messages_count = await message_service.cleanup_old_messages(365)

        empty_conversations_count = await message_service.cleanup_empty_conversations()

        return {
            "message": "Message system cleanup completed",
            "old_messages_removed": old_messages_count,
            "empty_conversations_removed": empty_conversations_count,
        }
    except Exception as e:
        return {
            "message": "Message cleanup failed",
            "error": str(e),
            "old_messages_removed": 0,
            "empty_conversations_removed": 0,
        }


@app.get("/api/admin/security-overview")
async def security_overview(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
):
    SecurityLogger.log_admin_action(
        request, admin_user_id=current_admin.id, action="view_security_overview"
    )

    return {
        "security_system": "structured_logging",
        "status": "active",
        "features": {
            "structured_logging": True,
            "rate_limiting": True,
            "failed_login_protection": True,
            "suspicious_activity_detection": True,
            "admin_action_auditing": True,
        },
        "note": "Detailed security metrics available through log aggregation system",
        "recommendation": "Set up ELK stack or similar for detailed security analytics",
    }


@app.post("/api/admin/tasks/trigger-cleanup")
async def trigger_cleanup(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
):
    try:
        SecurityLogger.log_admin_action(
            request, admin_user_id=current_admin.id, action="trigger_system_cleanup"
        )

        await scheduler_service.daily_cleanup()
        await run_maintenance()

        return {"message": "Cleanup triggered successfully (including token cleanup)"}
    except Exception as e:
        return {"message": f"Cleanup failed: {str(e)}"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    try:
        user_id = None
        user_email = None

        token = request.cookies.get("access_token")
        if token:
            from app.core.auth import verify_token

            payload = verify_token(token)
            if payload:
                user_id = payload.get("sub")

        error_traceback = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

        notify_telegram(
            TelegramNotifier.notify_error(
                error_type=type(exc).__name__,
                error_message=str(exc)[:200],
                user_id=int(user_id) if user_id else None,
                user_email=user_email,
                endpoint=str(request.url.path),
                traceback=error_traceback[:500],
            )
        )
    except Exception as notify_error:
        logger.error(f"Failed to send Telegram notification: {notify_error}")

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred",
        },
    )


@app.get("/api/stats")
async def public_platform_stats(db: Annotated[AsyncSession, Depends(get_db)]):
    from sqlalchemy import func, select

    try:
        user_count = await db.execute(select(func.count(User.id)).where(User.is_active))

        active_events = await db.execute(
            select(func.count(Event.id)).where(
                Event.is_active, Event.start_datetime > datetime.now(timezone.utc)
            )
        )

        active_services = await db.execute(
            select(func.count(Service.id)).where(Service.is_active)
        )

        active_polls = await db.execute(
            select(func.count(Poll.id)).where(Poll.is_active)
        )

        return {
            "community_size": user_count.scalar() or 0,
            "upcoming_events": active_events.scalar() or 0,
            "active_services": active_services.scalar() or 0,
            "active_polls": active_polls.scalar() or 0,
            "platform_version": settings.VERSION,
            "security_features": [
                "refresh_token_rotation",
                "automatic_cleanup",
                "structured_logging",
                "rate_limiting",
            ],
        }
    except Exception:
        return {
            "community_size": 0,
            "upcoming_events": 0,
            "active_services": 0,
            "active_polls": 0,
            "recent_messages": 0,
            "platform_version": settings.VERSION,
            "error": "Stats temporarily unavailable",
        }
