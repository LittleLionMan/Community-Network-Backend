from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone


from app.database import get_db
from app.core.dependencies import get_current_admin_user
from app.core.logging import SecurityLogger, rate_limiter

router = APIRouter(prefix="/admin/security", tags=["admin-security"])

@router.get("/events")
async def get_security_events(
    limit: int = Query(100, le=1000, description="Maximum number of events to return"),
    hours: int = Query(24, le=168, description="Hours to look back"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    level: Optional[str] = Query(None, description="Filter by security level"),
    current_admin = Depends(get_current_admin_user)
):
    """
    Get security events from application logs.

    Note: This is a simplified version. In production, you would:
    - Connect to your log aggregation system (ELK, Splunk, etc.)
    - Query structured logs from the past N hours
    - Filter by event types and levels
    """

    return {
        "message": "Security events now logged via structured logging",
        "info": "Check application logs for security events",
        "filters": {
            "hours": hours,
            "event_type": event_type,
            "level": level
        },
        "note": "Implement log aggregation system for full functionality"
    }

@router.get("/events/summary")
async def get_security_summary(
    hours: int = Query(24, le=168, description="Hours to look back"),
    current_admin = Depends(get_current_admin_user)
):
    return {
        "message": "Security summary now available through log analysis",
        "time_range": f"Last {hours} hours",
        "note": "Implement log aggregation for detailed metrics",
        "structured_logging": "enabled",
        "rate_limiting": "active"
    }

@router.get("/stats")
async def get_security_stats(
    hours: int = Query(24, le=168, description="Hours to analyze"),
    current_admin = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    return {
        "time_range": f"Last {hours} hours",
        "overview": {
            "structured_logging": "enabled",
            "rate_limiting": "active",
            "security_middleware": "active",
            "suspicious_request_detection": "active"
        },
        "security_health": {
            "status": "healthy",
            "structured_logging": True,
            "rate_limiting": True
        },
        "note": "Detailed metrics available through log aggregation system"
    }

@router.post("/test-logging")
async def test_security_logging(
    request: Request,
    current_admin = Depends(get_current_admin_user)
):
    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="test_security_logging",
        details={"test": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    )

    SecurityLogger.log_suspicious_activity(
        request,
        "admin_test",
        user_id=current_admin.id,
        details={"test_event": True}
    )

    return {
        "message": "Test security events logged successfully",
        "admin_user": current_admin.display_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Check application logs for the test events"
    }

@router.get("/rate-limit-status")
async def get_rate_limit_status(
    current_admin = Depends(get_current_admin_user)
):
    """Get current rate limiting status"""

    return {
        "rate_limiting": {
            "enabled": True,
            "type": "in_memory",
            "limits": {
                "login": "5 attempts per 15 minutes",
                "registration": "5 attempts per hour",
                "general_auth": "20 attempts per hour"
            }
        },
        "note": "Rate limiting active via in-memory store"
    }

@router.post("/clear-rate-limits")
async def clear_rate_limits(
    request: Request,
    ip_address: Optional[str] = Query(None, description="Clear limits for specific IP"),
    current_admin = Depends(get_current_admin_user)
):
    if ip_address:
        keys_to_clear = [k for k in rate_limiter._attempts.keys() if ip_address in k]
        lockouts_to_clear = [k for k in rate_limiter._lockouts.keys() if ip_address in k]

        for key in keys_to_clear:
            del rate_limiter._attempts[key]
        for key in lockouts_to_clear:
            del rate_limiter._lockouts[key]

        message = f"Rate limits cleared for IP: {ip_address}"
    else:
        rate_limiter._attempts.clear()
        rate_limiter._lockouts.clear()
        message = "All rate limits cleared"

    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="clear_rate_limits",
        details={"ip_address": ip_address, "cleared_all": ip_address is None}
    )

    return {
        "message": message,
        "admin_user": current_admin.display_name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
