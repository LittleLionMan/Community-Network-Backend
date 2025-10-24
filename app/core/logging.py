import logging
import json
from datetime import datetime, timezone
from fastapi import Request
from app.core.telegram import TelegramNotifier, notify_telegram


def get_client_ip(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip", "")
        or getattr(request.client, "host", "unknown")
        if request.client
        else "unknown"
    )


def get_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "unknown")


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

security_logger = logging.getLogger("security")
auth_logger = logging.getLogger("auth")
admin_logger = logging.getLogger("admin")


class SecurityLogger:
    @staticmethod
    def log_login_attempt(
        request: Request,
        email: str,
        success: bool,
        user_id: int | None = None,
        failure_reason: str | None = None,
        additional_data: dict[str, object] | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = (
            f"Login {'successful' if success else 'failed'}: {json.dumps(log_data)}"
        )

        if success:
            auth_logger.info(message)
        else:
            auth_logger.warning(message)

    @staticmethod
    def log_registration(
        request: Request,
        email: str,
        user_id: int | None = None,
        success: bool = True,
        failure_reason: str | None = None,
        display_name: str | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = f"Registration {'successful' if success else 'failed'}: {json.dumps(log_data)}"

        if success:
            auth_logger.info(message)
            if user_id and display_name:
                notify_telegram(
                    TelegramNotifier.notify_new_user(email, display_name, user_id)
                )
        else:
            auth_logger.warning(message)

    @staticmethod
    def log_password_reset(
        request: Request,
        email: str,
        step: str,
        user_id: int | None = None,
        additional_data: dict[str, object] | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = f"Password reset {step}: {json.dumps(log_data)}"

        if step == "failed":
            auth_logger.warning(message)
        else:
            auth_logger.info(message)

    @staticmethod
    def log_email_change(
        request: Request,
        user_id: int,
        old_email: str,
        new_email: str,
        step: str,
        additional_data: dict[str, object] | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = f"Email change {step}: {json.dumps(log_data)}"
        security_logger.info(message)

    @staticmethod
    def log_suspicious_activity(
        request: Request,
        activity_type: str,
        user_id: int | None = None,
        email: str | None = None,
        details: dict[str, object] | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = f"Suspicious activity detected: {json.dumps(log_data)}"
        security_logger.warning(message)

    @staticmethod
    def log_admin_action(
        request: Request,
        admin_user_id: int,
        action: str,
        target_user_id: int | None = None,
        details: dict[str, object] | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = f"Admin action - {action}: {json.dumps(log_data)}"
        admin_logger.info(message)

    @staticmethod
    def log_rate_limit_exceeded(
        request: Request,
        limit_type: str,
        user_id: int | None = None,
        details: dict[str, object] | None = None,
    ):
        log_data: dict[str, object] = {
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

        message = f"Rate limit exceeded: {json.dumps(log_data)}"
        security_logger.warning(message)
        notify_telegram(
            TelegramNotifier.notify_rate_limit_exceeded(
                limit_type=limit_type,
                ip_address=get_client_ip(request),
                user_id=user_id,
                attempts=details.get("attempts", 0) if details else 0,
            )
        )


class SimpleRateLimiter:
    def __init__(self):
        self._attempts: dict[str, list[tuple[float, int]]] = {}
        self._lockouts: dict[str, float] = {}

    def check_and_record_attempt(
        self,
        key: str,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 900,
    ) -> dict[str, object]:
        import time

        now = time.time()

        if key in self._lockouts:
            if now < self._lockouts[key]:
                return {
                    "allowed": False,
                    "reason": "locked_out",
                    "retry_after": int(self._lockouts[key] - now),
                }
            else:
                del self._lockouts[key]

        if key in self._attempts:
            self._attempts[key] = [
                (timestamp, count)
                for timestamp, count in self._attempts[key]
                if now - timestamp < window_seconds
            ]

        current_attempts = sum(
            count for _timestamp, count in self._attempts.get(key, [])
        )

        if current_attempts >= max_attempts:
            self._lockouts[key] = now + lockout_seconds
            return {
                "allowed": False,
                "reason": "too_many_attempts",
                "attempts": current_attempts,
                "retry_after": lockout_seconds,
            }

        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append((now, 1))

        return {
            "allowed": True,
            "attempts": current_attempts + 1,
            "remaining": max_attempts - current_attempts - 1,
        }

    def clear_ip_limits(self, ip_address: str) -> int:
        keys_to_clear = [k for k in self._attempts.keys() if ip_address in k]
        lockouts_to_clear = [k for k in self._lockouts.keys() if ip_address in k]

        for key in keys_to_clear:
            del self._attempts[key]
        for key in lockouts_to_clear:
            del self._lockouts[key]

        return len(keys_to_clear) + len(lockouts_to_clear)

    def clear_all_limits(self) -> None:
        self._attempts.clear()
        self._lockouts.clear()


rate_limiter = SimpleRateLimiter()
