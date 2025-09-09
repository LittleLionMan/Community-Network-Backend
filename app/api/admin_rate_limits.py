from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
from datetime import datetime

from app.core.dependencies import get_current_admin_user
from app.core.content_rate_limiter import content_rate_limiter, ContentType
from app.core.rate_limit_decorator import read_rate_limiter
from app.core.logging import SecurityLogger
from app.models.user import User

router = APIRouter(prefix="/admin/rate-limits", tags=["admin-rate-limits"])

@router.get("/user/{user_id}/stats")
async def get_user_rate_limit_stats(
    request: Request,
    user_id: int,
    current_admin: User = Depends(get_current_admin_user)
):
    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="view_user_rate_limits",
        target_user_id=user_id
    )

    stats = content_rate_limiter.get_user_stats(user_id)

    return {
        "user_id": user_id,
        "content_usage": stats["usage"],
        "active_lockouts": stats["lockouts"],
        "timestamp": datetime.now().isoformat()
    }

@router.post("/user/{user_id}/clear")
async def clear_user_rate_limits(
    request: Request,
    user_id: int,
    content_type: Optional[str] = Query(None, description="Specific content type to clear"),
    current_admin: User = Depends(get_current_admin_user)
):
    content_type_enum = None
    if content_type:
        try:
            content_type_enum = ContentType(content_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content type. Valid types: {[ct.value for ct in ContentType]}"
            )

    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="clear_user_rate_limits",
        target_user_id=user_id,
        details={"content_type": content_type}
    )

    content_rate_limiter.clear_user_limits(user_id, content_type_enum)

    return {
        "message": f"Rate limits cleared for user {user_id}",
        "content_type": content_type or "all",
        "admin_user": current_admin.display_name
    }

@router.get("/overview")
async def get_rate_limit_overview(
    request: Request,
    current_admin: User = Depends(get_current_admin_user)
):

    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_admin.id,
        action="view_rate_limit_overview"
    )

    active_users = len([
        user_id for user_id, attempts in content_rate_limiter.attempts.items()
        if any(attempts.values())
    ])

    active_lockouts = len(content_rate_limiter.lockouts)

    read_active_ips = len(read_rate_limiter.attempts)

    return {
        "content_rate_limits": {
            "active_users": active_users,
            "active_lockouts": active_lockouts,
            "total_tracked_users": len(content_rate_limiter.attempts)
        },
        "read_rate_limits": {
            "active_ips": read_active_ips,
            "total_tracked_ips": len(read_rate_limiter.attempts)
        },
        "rate_limit_config": {
            "content_types": [ct.value for ct in ContentType],
            "user_tiers": ["new", "regular", "established", "trusted"]
        }
    }
