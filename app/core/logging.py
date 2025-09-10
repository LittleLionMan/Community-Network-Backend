import logging
import structlog
import sys
from typing import Any, Dict, Optional
from datetime import datetime, timezone

def get_client_ip(request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip", "") or
        getattr(request.client, 'host', 'unknown') if request.client else "unknown"
    )

def get_user_agent(request) -> str:
    """Extract user agent from request"""
    return request.headers.get("user-agent", "unknown")

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if sys.stdout.isatty() else structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.WriteLoggerFactory(),
    cache_logger_on_first_use=True,
)

security_logger = structlog.get_logger("security")
auth_logger = structlog.get_logger("auth")
admin_logger = structlog.get_logger("admin")

class SecurityLogger:

    @staticmethod
    def log_login_attempt(
        request,
        email: str,
        success: bool,
        user_id: Optional[int] = None,
        failure_reason: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        log_data = {
            "event_type": "login_attempt",
            "email": email,
            "success": success,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            log_data["user_id"] = user_id
        if failure_reason:
            log_data["failure_reason"] = failure_reason
        if additional_data:
            log_data.update(additional_data)

        if success:
            auth_logger.info("Login successful", **log_data)
        else:
            auth_logger.warning("Login failed", **log_data)

    @staticmethod
    def log_registration(
        request,
        email: str,
        user_id: Optional[int] = None,
        success: bool = True,
        failure_reason: Optional[str] = None
    ):
        log_data = {
            "event_type": "user_registration",
            "email": email,
            "success": success,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            log_data["user_id"] = user_id
        if failure_reason:
            log_data["failure_reason"] = failure_reason

        if success:
            auth_logger.info("Registration successful", **log_data)
        else:
            auth_logger.warning("Registration failed", **log_data)

    @staticmethod
    def log_password_reset(
        request,
        email: str,
        step: str,
        user_id: Optional[int] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        log_data = {
            "event_type": "password_reset",
            "step": step,
            "email": email,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            log_data["user_id"] = str(user_id)
        if additional_data:
            log_data.update(additional_data)

        if step == "failed":
            auth_logger.warning("Password reset failed", **log_data)
        else:
            auth_logger.info(f"Password reset {step}", **log_data)

    @staticmethod
    def log_email_change(
        request,
        user_id: int,
        old_email: str,
        new_email: str,
        step: str,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        log_data = {
            "event_type": "email_change",
            "step": step,
            "user_id": user_id,
            "old_email": old_email,
            "new_email": new_email,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if additional_data:
            log_data.update(additional_data)

        security_logger.info(f"Email change {step}", **log_data)

    @staticmethod
    def log_suspicious_activity(
        request,
        activity_type: str,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        log_data = {
            "event_type": "suspicious_activity",
            "activity_type": activity_type,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            log_data["user_id"] = str(user_id)
        if email:
            log_data["email"] = email
        if details:
            log_data.update(details)

        security_logger.warning("Suspicious activity detected", **log_data)

    @staticmethod
    def log_admin_action(
        request,
        admin_user_id: int,
        action: str,
        target_user_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        log_data = {
            "event_type": "admin_action",
            "admin_user_id": admin_user_id,
            "action": action,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if target_user_id:
            log_data["target_user_id"] = target_user_id
        if details:
            log_data.update(details)

        admin_logger.info(f"Admin action: {action}", **log_data)

    @staticmethod
    def log_rate_limit_exceeded(
        request,
        limit_type: str,
        user_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        log_data = {
            "event_type": "rate_limit_exceeded",
            "limit_type": limit_type,
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id is not None:
            log_data["user_id"] = str(user_id)
        if details is not None:
            log_data.update(details)

        security_logger.warning("Rate limit exceeded", **log_data)

class SimpleRateLimiter:

    def __init__(self):
        self._attempts = {}
        self._lockouts = {}

    def check_and_record_attempt(
        self,
        key: str,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 900
    ) -> Dict[str, Any]:
        import time

        now = time.time()

        if key in self._lockouts:
            if now < self._lockouts[key]:
                return {
                    "allowed": False,
                    "reason": "locked_out",
                    "retry_after": int(self._lockouts[key] - now)
                }
            else:
                del self._lockouts[key]

        if key in self._attempts:
            self._attempts[key] = [
                (timestamp, count) for timestamp, count in self._attempts[key]
                if now - timestamp < window_seconds
            ]

        current_attempts = sum(
            count for timestamp, count in self._attempts.get(key, [])
        )

        if current_attempts >= max_attempts:
            self._lockouts[key] = now + lockout_seconds
            return {
                "allowed": False,
                "reason": "too_many_attempts",
                "attempts": current_attempts,
                "retry_after": lockout_seconds
            }

        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append((now, 1))

        return {
            "allowed": True,
            "attempts": current_attempts + 1,
            "remaining": max_attempts - current_attempts - 1
        }

rate_limiter = SimpleRateLimiter()
