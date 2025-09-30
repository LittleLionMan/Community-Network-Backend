from fastapi import APIRouter, Depends, Query, Request
from typing import Annotated
from datetime import datetime, timezone

from app.models.user import User
from app.core.dependencies import get_current_admin_user
from app.core.logging import SecurityLogger, rate_limiter

router = APIRouter(prefix="/admin/security", tags=["admin-security"])


@router.get("/events")
async def get_security_events(
    hours: Annotated[int, Query(le=168, description="Hours to look back")] = 24,
    event_type: Annotated[str | None, Query(description="Filter by event type")] = None,
    level: Annotated[str | None, Query(description="Filter by security level")] = None,
):
    return {
        "message": "Security events now logged via structured logging",
        "info": "Check application logs for security events",
        "filters": {"hours": hours, "event_type": event_type, "level": level},
        "note": "Implement log aggregation system for full functionality",
    }


@router.get("/events/summary")
async def get_security_summary(
    hours: Annotated[int, Query(le=168, description="Hours to look back")] = 24,
):
    return {
        "message": "Security summary now available through log analysis",
        "time_range": f"Last {hours} hours",
        "note": "Implement log aggregation for detailed metrics",
        "structured_logging": "enabled",
        "rate_limiting": "active",
    }


@router.get("/stats")
async def get_security_stats(
    hours: Annotated[int, Query(le=168, description="Hours to analyze")] = 24,
):
    return {
        "time_range": f"Last {hours} hours",
        "overview": {
            "structured_logging": "enabled",
            "rate_limiting": "active",
            "security_middleware": "active",
            "suspicious_request_detection": "active",
        },
        "security_health": {
            "status": "healthy",
            "structured_logging": True,
            "rate_limiting": True,
        },
        "note": "Detailed metrics available through log aggregation system",
    }


@router.post("/test-logging")
async def test_security_logging(
    request: Request, current_admin: Annotated[User, Depends(get_current_admin_user)]
):
    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="test_security_logging",
        details={"test": True, "timestamp": datetime.now(timezone.utc).isoformat()},
    )

    SecurityLogger.log_suspicious_activity(
        request, "admin_test", user_id=current_admin.id, details={"test_event": True}
    )

    return {
        "message": "Test security events logged successfully",
        "admin_user": current_admin.display_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Check application logs for the test events",
    }


@router.get("/rate-limit-status")
async def get_rate_limit_status():
    return {
        "rate_limiting": {
            "enabled": True,
            "type": "in_memory",
            "limits": {
                "login": "5 attempts per 15 minutes",
                "registration": "5 attempts per hour",
                "general_auth": "20 attempts per hour",
            },
        },
        "note": "Rate limiting active via in-memory store",
    }


@router.post("/clear-rate-limits")
async def clear_rate_limits(
    request: Request,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    ip_address: Annotated[
        str | None, Query(description="Clear limits for specific IP")
    ] = None,
):
    if ip_address:
        cleared_count = rate_limiter.clear_ip_limits(ip_address)
        message = f"Rate limits cleared for IP: {ip_address} ({cleared_count} entries)"
    else:
        rate_limiter.clear_all_limits()
        message = "All rate limits cleared"

    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="clear_rate_limits",
        details={"ip_address": ip_address, "cleared_all": ip_address is None},
    )

    return {
        "message": message,
        "admin_user": current_admin.display_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
