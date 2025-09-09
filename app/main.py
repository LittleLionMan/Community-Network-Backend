from fastapi import FastAPI, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
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
from app.api import auth, users, event_categories, events, services, discussions, comments, polls, forum_categories, messages, admin_security
from app.database import get_db
from app.core.dependencies import get_current_admin_user
from app.services.scheduler_service import scheduler_service

from app.core.background_tasks import startup_background_tasks, shutdown_background_tasks, run_maintenance

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = structlog.get_logger()
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
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(admin_security.router, prefix="/api", tags=["admin-security"])

@app.get("/health")
async def health_check(request: Request):
    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "timestamp": datetime.now().isoformat(),
        "features": {
            "authentication": True,
            "refresh_token_rotation": True,
            "security_monitoring": True,
            "failed_login_protection": True,
            "ip_blocking": True,
            "events": True,
            "services": True,
            "forum": True,
            "polling": True,
            "messages": True,
            "content_moderation": settings.CONTENT_MODERATION_ENABLED,
            "service_matching": getattr(settings, 'SERVICE_MATCHING_ENABLED', True),
            "auto_attendance": getattr(settings, 'EVENT_AUTO_ATTENDANCE_ENABLED', True),
            "websocket_messaging": True,
            "background_tasks": True,
            "token_cleanup": True,
            "request_monitoring": True
        }
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
            "replay_attack_prevention"
        ]
    }

@app.get("/api/admin/dashboard")
async def admin_dashboard(
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    from app.models.user import User
    from app.models.event import Event
    from app.models.service import Service
    from app.models.comment import Comment
    from app.models.forum import ForumPost
    from app.models.poll import Poll, Vote
    from app.models.message import Message, Conversation
    from app.models.auth import RefreshToken

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

        message_count = await db.execute(select(func.count(Message.id)))
        conversation_count = await db.execute(select(func.count(Conversation.id)))
        active_conversations = await db.execute(
            select(func.count(Conversation.id)).where(Conversation.is_active == True)
        )
        flagged_messages = await db.execute(
            select(func.count(Message.id)).where(Message.is_flagged == True)
        )

        stats['total_messages'] = message_count.scalar() or 0
        stats['total_conversations'] = conversation_count.scalar() or 0
        stats['active_conversations'] = active_conversations.scalar() or 0
        stats['flagged_messages'] = flagged_messages.scalar() or 0

        active_tokens = await db.execute(
            select(func.count(RefreshToken.id)).where(RefreshToken.is_revoked == False)
        )
        total_tokens = await db.execute(select(func.count(RefreshToken.id)))

        stats['active_refresh_tokens'] = active_tokens.scalar() or 0
        stats['total_refresh_tokens'] = total_tokens.scalar() or 0

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
            'total_messages': 0,
            'active_refresh_tokens': 0,
            'total_refresh_tokens': 0,
            'recent_activity': {
                'new_users_7d': 0,
                'new_events_7d': 0,
                'new_services_7d': 0,
                'new_messages_7d': 0
            },
            'error': str(e)
        }

    try:
        from app.services.security_service import SecurityService
        security_service = SecurityService(db)

        recent_events = await security_service.get_security_events(hours=24, limit=1000)

        failed_logins_24h = len([e for e in recent_events if e.event_type.value == "failed_login"])
        suspicious_activities_24h = len([e for e in recent_events if e.event_type.value == "suspicious_activity"])
        high_priority_events_24h = len([e for e in recent_events if e.level.value in ["high", "critical"]])

        stats['security_monitoring'] = {
            'total_events_24h': len(recent_events),
            'failed_logins_24h': failed_logins_24h,
            'suspicious_activities_24h': suspicious_activities_24h,
            'high_priority_events_24h': high_priority_events_24h,
            'monitoring_active': True
        }

    except Exception as e:
        stats['security_monitoring'] = {
            'total_events_24h': 0,
            'failed_logins_24h': 0,
            'suspicious_activities_24h': 0,
            'high_priority_events_24h': 0,
            'monitoring_active': False,
            'error': str(e)
        }

    from app.services.websocket_service import websocket_manager
    ws_stats = websocket_manager.get_connection_stats()

    return {
        'platform_stats': stats,
        'websocket_stats': ws_stats,
        'health': {
            'database': 'connected',
            'moderation': 'active' if settings.CONTENT_MODERATION_ENABLED else 'disabled',
            'matching': 'active' if getattr(settings, 'SERVICE_MATCHING_ENABLED', True) else 'disabled',
            'messaging': 'active',
            'websockets': 'active',
            'token_rotation': 'active',
            'security_monitoring_enabled': True,
            'failed_login_protection': True,
            'request_monitoring': True
        },
        'settings': {
            'debug_mode': settings.DEBUG,
            'content_moderation_enabled': settings.CONTENT_MODERATION_ENABLED,
            'moderation_threshold': getattr(settings, 'MODERATION_THRESHOLD', 0.7),
            'service_matching_enabled': getattr(settings, 'SERVICE_MATCHING_ENABLED', True),
            'event_auto_attendance': getattr(settings, 'EVENT_AUTO_ATTENDANCE_ENABLED', True),
            'message_system_enabled': True,
            'refresh_token_rotation': True
        }
    }

@app.post("/api/admin/maintenance/tokens")
async def trigger_token_maintenance(current_admin = Depends(get_current_admin_user)):
    try:
        await run_maintenance()
        return {
            "status": "success",
            "message": "Token maintenance completed successfully"
        }
    except Exception as e:
        logger = structlog.get_logger()
        logger.error(f"Manual token maintenance failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Token maintenance failed",
                "error": str(e)
            }
        )

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

@app.post("/api/admin/tasks/cleanup-messages")
async def cleanup_message_system(
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    from app.services.message_service import MessageService

    try:
        message_service = MessageService(db)

        old_messages_count = await message_service.cleanup_old_messages(365)

        empty_conversations_count = await message_service.cleanup_empty_conversations()

        return {
            "message": "Message system cleanup completed",
            "old_messages_removed": old_messages_count,
            "empty_conversations_removed": empty_conversations_count
        }
    except Exception as e:
        return {
            "message": "Message cleanup failed",
            "error": str(e),
            "old_messages_removed": 0,
            "empty_conversations_removed": 0
        }

@app.get("/api/admin/security-overview")
async def security_overview(
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        from app.services.security_service import SecurityService
        security_service = SecurityService(db)

        events_24h = await security_service.get_security_events(hours=24, limit=1000)

        events_7d = await security_service.get_security_events(hours=168, limit=5000)

        failed_logins_24h = len([e for e in events_24h if e.event_type.value == "failed_login"])
        failed_logins_7d = len([e for e in events_7d if e.event_type.value == "failed_login"])

        suspicious_24h = len([e for e in events_24h if e.event_type.value == "suspicious_activity"])
        suspicious_7d = len([e for e in events_7d if e.event_type.value == "suspicious_activity"])

        failed_login_events = [e for e in events_24h if e.event_type.value == "failed_login"]
        ip_counts = {}
        for event in failed_login_events:
            ip = event.ip_address
            ip_counts[ip] = ip_counts.get(ip, 0) + 1

        top_failed_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        health_score = 100
        if failed_logins_24h > 50:
            health_score -= 20
        if suspicious_24h > 20:
            health_score -= 15
        if len([e for e in events_24h if e.level.value in ["high", "critical"]]) > 5:
            health_score -= 25

        health_score = max(0, health_score)

        return {
            "security_health_score": health_score,
            "status": "healthy" if health_score >= 80 else "warning" if health_score >= 60 else "critical",
            "metrics_24h": {
                "total_events": len(events_24h),
                "failed_logins": failed_logins_24h,
                "suspicious_activities": suspicious_24h,
                "high_priority_events": len([e for e in events_24h if e.level.value in ["high", "critical"]])
            },
            "trends_7d": {
                "total_events": len(events_7d),
                "failed_logins": failed_logins_7d,
                "suspicious_activities": suspicious_7d,
                "daily_average_events": len(events_7d) // 7
            },
            "top_threats": {
                "failed_login_ips": top_failed_ips,
                "blocked_ips_count": await get_blocked_ips_count(security_service)
            },
            "recommendations": generate_security_recommendations(
                failed_logins_24h, suspicious_24h, health_score
            )
        }

    except Exception as e:
        return {
            "error": "Failed to generate security overview",
            "detail": str(e),
            "security_health_score": 0,
            "status": "error"
        }

async def get_blocked_ips_count(security_service) -> int:
    try:
        blocked_keys = await security_service._redis_keys("blocked_ip:*")
        return len(blocked_keys)
    except:
        return 0

def generate_security_recommendations(failed_logins: int, suspicious: int, health_score: int) -> list:
    recommendations = []

    if failed_logins > 50:
        recommendations.append({
            "priority": "high",
            "title": "High Failed Login Activity",
            "description": f"{failed_logins} failed logins in 24h. Consider reviewing login security.",
            "action": "Review top failing IPs and consider IP blocking"
        })

    if suspicious > 20:
        recommendations.append({
            "priority": "medium",
            "title": "Suspicious Activity Detected",
            "description": f"{suspicious} suspicious activities detected.",
            "action": "Review security events and investigate patterns"
        })

    if health_score < 70:
        recommendations.append({
            "priority": "high",
            "title": "Security Health Score Low",
            "description": f"Current security score: {health_score}/100",
            "action": "Immediate security review recommended"
        })

    if not recommendations:
        recommendations.append({
            "priority": "low",
            "title": "Security Status Good",
            "description": "No immediate security concerns detected",
            "action": "Continue monitoring"
        })

    return recommendations

@app.post("/api/admin/tasks/trigger-cleanup")
async def trigger_cleanup(
    current_admin = Depends(get_current_admin_user)
):
    try:
        await scheduler_service.daily_cleanup()

        await run_maintenance()

        return {"message": "Cleanup triggered successfully (including token cleanup)"}
    except Exception as e:
        return {"message": f"Cleanup failed: {str(e)}"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = structlog.get_logger()
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred"
        }
    )

@app.get("/api/stats")
async def public_platform_stats(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func, select
    from app.models.user import User
    from app.models.event import Event
    from app.models.service import Service
    from app.models.poll import Poll
    from app.models.message import Message

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

        recent_messages = await db.execute(
            select(func.count(Message.id)).where(
                Message.created_at > datetime.now() - timedelta(days=30)
            )
        )

        return {
            "community_size": user_count.scalar() or 0,
            "upcoming_events": active_events.scalar() or 0,
            "active_services": active_services.scalar() or 0,
            "active_polls": active_polls.scalar() or 0,
            "platform_version": settings.VERSION,
            "security_features": ["refresh_token_rotation", "automatic_cleanup"]
        }
    except Exception as e:
        return {
            "community_size": 0,
            "upcoming_events": 0,
            "active_services": 0,
            "active_polls": 0,
            "recent_messages": 0,
            "platform_version": settings.VERSION,
            "error": "Stats temporarily unavailable"
        }
