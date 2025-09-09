from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timedelta, timezone
import json

from app.database import get_db
from app.core.dependencies import get_current_admin_user
from app.services.security_service import SecurityService, SecurityEventType, SecurityLevel

router = APIRouter(prefix="/admin/security", tags=["admin-security"])

async def get_security_service(db: AsyncSession = Depends(get_db)) -> SecurityService:
    return SecurityService(db)

@router.get("/events")
async def get_security_events(
    limit: int = Query(100, le=1000, description="Maximum number of events to return"),
    hours: int = Query(24, le=168, description="Hours to look back"),
    event_type: Optional[SecurityEventType] = Query(None, description="Filter by event type"),
    level: Optional[SecurityLevel] = Query(None, description="Filter by security level"),
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service)
):

    events = await security_service.get_security_events(
        limit=limit,
        event_type=event_type,
        level=level,
        hours=hours
    )

    return {
        "events": [event.to_dict() for event in events],
        "total_events": len(events),
        "filters": {
            "hours": hours,
            "event_type": event_type.value if event_type else None,
            "level": level.value if level else None
        },
        "event_types": [e.value for e in SecurityEventType],
        "security_levels": [l.value for l in SecurityLevel]
    }

@router.get("/events/summary")
async def get_security_summary(
    hours: int = Query(24, le=168, description="Hours to look back"),
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service)
):

    events = await security_service.get_security_events(
        limit=10000,
        hours=hours
    )

    event_counts = {}
    level_counts = {}
    hourly_counts = {}

    for event in events:
        event_type = event.event_type.value
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

        level = event.level.value
        level_counts[level] = level_counts.get(level, 0) + 1

        hour = event.timestamp.strftime('%Y-%m-%d %H:00')
        hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

    failed_login_events = [e for e in events if e.event_type == SecurityEventType.FAILED_LOGIN]
    ip_failed_counts = {}
    for event in failed_login_events:
        ip = event.ip_address
        ip_failed_counts[ip] = ip_failed_counts.get(ip, 0) + 1

    top_failed_ips = sorted(ip_failed_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "summary": {
            "total_events": len(events),
            "time_range_hours": hours,
            "high_priority_events": len([e for e in events if e.level in [SecurityLevel.HIGH, SecurityLevel.CRITICAL]]),
            "failed_logins": len(failed_login_events),
            "suspicious_activities": len([e for e in events if e.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY])
        },
        "event_counts_by_type": event_counts,
        "event_counts_by_level": level_counts,
        "hourly_distribution": hourly_counts,
        "top_failed_login_ips": top_failed_ips
    }

@router.get("/ip/{ip_address}")
async def get_ip_reputation(
    ip_address: str,
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service)
):

    reputation = await security_service.get_ip_reputation(ip_address)

    all_events = await security_service.get_security_events(limit=1000, hours=168)
    ip_events = [e for e in all_events if e.ip_address == ip_address]

    return {
        "ip_address": ip_address,
        "reputation": reputation,
        "recent_events": [event.to_dict() for event in ip_events[:50]],
        "event_summary": {
            "total_events": len(ip_events),
            "failed_logins": len([e for e in ip_events if e.event_type == SecurityEventType.FAILED_LOGIN]),
            "successful_logins": len([e for e in ip_events if e.event_type == SecurityEventType.SUCCESSFUL_LOGIN]),
            "suspicious_activities": len([e for e in ip_events if e.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY])
        }
    }

@router.post("/ip/{ip_address}/block")
async def block_ip_address(
    ip_address: str,
    request: Request,
    duration_minutes: int = Query(60, ge=1, le=10080, description="Block duration in minutes (max 1 week)"),
    reason: str = Query(..., description="Reason for blocking"),
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service)
):

    try:
        block_key = f"blocked_ip:{ip_address}"
        security_service._redis_set(
            block_key,
            json.dumps({
                "blocked_by": current_admin.id,
                "reason": reason,
                "blocked_at": datetime.now(timezone.utc).isoformat()
            }),
            ex=duration_minutes * 60
        )

        await security_service.log_security_event(
            SecurityEventType.ACCOUNT_LOCKED,
            SecurityLevel.HIGH,
            request,
            user_id=current_admin.id,
            details={
                "action": "admin_ip_block",
                "blocked_ip": ip_address,
                "duration_minutes": duration_minutes,
                "reason": reason
            }
        )

        return {
            "message": f"IP {ip_address} blocked successfully",
            "blocked_until": (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).isoformat(),
            "reason": reason
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to block IP: {str(e)}"
        )

@router.delete("/ip/{ip_address}/block")
async def unblock_ip_address(
    ip_address: str,
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service)
):

    try:
        block_key = f"blocked_ip:{ip_address}"
        security_service._redis_delete(block_key)

        return {
            "message": f"IP {ip_address} unblocked successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unblock IP: {str(e)}"
        )

@router.get("/stats")
async def get_security_stats(
    hours: int = Query(24, le=168, description="Hours to analyze"),
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service),
    db: AsyncSession = Depends(get_db)
):

    events = await security_service.get_security_events(limit=10000, hours=hours)

    failed_logins = [e for e in events if e.event_type == SecurityEventType.FAILED_LOGIN]
    successful_logins = [e for e in events if e.event_type == SecurityEventType.SUCCESSFUL_LOGIN]
    suspicious_activities = [e for e in events if e.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY]

    unique_ips = len(set(e.ip_address for e in events))

    total_login_attempts = len(failed_logins) + len(successful_logins)
    failed_login_rate = (len(failed_logins) / total_login_attempts * 100) if total_login_attempts > 0 else 0

    ip_activity = {}
    for event in events:
        ip = event.ip_address
        ip_activity[ip] = ip_activity.get(ip, 0) + 1

    most_active_ips = sorted(ip_activity.items(), key=lambda x: x[1], reverse=True)[:10]

    level_distribution = {}
    for event in events:
        level = event.level.value
        level_distribution[level] = level_distribution.get(level, 0) + 1

    return {
        "time_range": f"Last {hours} hours",
        "overview": {
            "total_events": len(events),
            "unique_ips": unique_ips,
            "failed_logins": len(failed_logins),
            "successful_logins": len(successful_logins),
            "suspicious_activities": len(suspicious_activities),
            "failed_login_rate_percent": round(failed_login_rate, 2)
        },
        "top_metrics": {
            "most_active_ips": most_active_ips,
            "security_level_distribution": level_distribution
        },
        "security_health": {
            "status": "healthy" if failed_login_rate < 20 else "warning" if failed_login_rate < 50 else "critical",
            "failed_login_threshold": 20,  # percent
            "suspicious_activity_count": len(suspicious_activities),
            "high_priority_events": len([e for e in events if e.level in [SecurityLevel.HIGH, SecurityLevel.CRITICAL]])
        }
    }

@router.post("/alerts/test")
async def test_security_alert(
    current_admin = Depends(get_current_admin_user),
    security_service: SecurityService = Depends(get_security_service)
):
    return {
        "message": "Test security alert triggered",
        "admin_user": current_admin.display_name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
