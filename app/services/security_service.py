import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from enum import Enum
from dataclasses import dataclass, asdict
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request


try:
    from redis import Redis
    from ..database import redis_client
except ImportError:
    Redis = None
    redis_client = None

logger = logging.getLogger(__name__)

class SecurityEventType(str, Enum):
    FAILED_LOGIN = "failed_login"
    SUCCESSFUL_LOGIN = "successful_login"
    PASSWORD_RESET = "password_reset"
    EMAIL_CHANGE = "email_change"
    ACCOUNT_LOCKED = "account_locked"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    TOKEN_THEFT_ATTEMPT = "token_theft_attempt"
    MULTIPLE_DEVICE_LOGIN = "multiple_device_login"

class SecurityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityEvent:
    event_type: SecurityEventType
    level: SecurityLevel
    user_id: Optional[int]
    email: Optional[str]
    ip_address: str
    user_agent: str
    timestamp: datetime
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SecurityEvent':
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['event_type'] = SecurityEventType(data['event_type'])
        data['level'] = SecurityLevel(data['level'])
        return cls(**data)

class SecurityService:

    def __init__(self, db: AsyncSession, redis_client_instance: Any = None):
        self.db = db
        self.redis = redis_client_instance or redis_client

        # Configuration
        self.failed_login_threshold = 5
        self.failed_login_window = 300
        self.lockout_duration = 900
        self.suspicious_threshold = 10

    def get_client_info(self, request: Request) -> tuple[str, str]:
        ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip", "") or
            request.client.host if request.client else "unknown"
        )

        user_agent = request.headers.get("user-agent", "unknown")
        return ip, user_agent

    async def log_security_event(
        self,
        event_type: SecurityEventType,
        level: SecurityLevel,
        request: Request,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        ip_address, user_agent = self.get_client_info(request)

        event = SecurityEvent(
            event_type=event_type,
            level=level,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.now(timezone.utc),
            details=details or {}
        )

        try:
            key = f"security_event:{event.timestamp.timestamp()}"
            self._redis_set(key, json.dumps(event.to_dict()), ex=30*24*3600)

            self._track_ip_activity(ip_address, event)

            if user_id:
                self._track_user_activity(user_id, event)

            logger.info(
                f"Security event logged: {event_type.value} from {ip_address}",
                extra={
                    "event_type": event_type.value,
                    "level": level.value,
                    "user_id": user_id,
                    "ip_address": ip_address
                }
            )

        except Exception as e:
            logger.error(f"Failed to log security event: {e}")

    async def check_failed_login_attempts(
        self,
        request: Request,
        email: str
    ) -> Dict[str, Any]:
        ip_address, _ = self.get_client_info(request)

        ip_key = f"failed_login_ip:{ip_address}"
        ip_attempts = self._redis_get_int(ip_key)

        email_key = f"failed_login_email:{email}"
        email_attempts = self._redis_get_int(email_key)

        ip_locked = ip_attempts >= self.failed_login_threshold
        email_locked = email_attempts >= self.failed_login_threshold

        return {
            "ip_locked": ip_locked,
            "email_locked": email_locked,
            "ip_attempts": ip_attempts,
            "email_attempts": email_attempts,
            "max_attempts": self.failed_login_threshold,
            "lockout_duration": self.lockout_duration
        }

    async def record_failed_login(
        self,
        request: Request,
        email: str,
        reason: str = "invalid_credentials"
    ) -> Dict[str, Any]:
        ip_address, user_agent = self.get_client_info(request)

        # Increment counters
        ip_key = f"failed_login_ip:{ip_address}"
        email_key = f"failed_login_email:{email}"

        ip_attempts = self._redis_incr(ip_key, self.failed_login_window)
        email_attempts = self._redis_incr(email_key, self.failed_login_window)

        level = SecurityLevel.LOW
        if ip_attempts >= 3 or email_attempts >= 3:
            level = SecurityLevel.MEDIUM
        if ip_attempts >= self.failed_login_threshold or email_attempts >= self.failed_login_threshold:
            level = SecurityLevel.HIGH

        await self.log_security_event(
            SecurityEventType.FAILED_LOGIN,
            level,
            request,
            email=email,
            details={
                "reason": reason,
                "ip_attempts": ip_attempts,
                "email_attempts": email_attempts,
                "threshold_reached": ip_attempts >= self.failed_login_threshold or email_attempts >= self.failed_login_threshold
            }
        )

        return {
            "ip_attempts": ip_attempts,
            "email_attempts": email_attempts,
            "blocked": ip_attempts >= self.failed_login_threshold or email_attempts >= self.failed_login_threshold
        }

    async def record_successful_login(
        self,
        request: Request,
        user_id: int,
        email: str
    ) -> None:
        ip_address, _ = self.get_client_info(request)

        ip_key = f"failed_login_ip:{ip_address}"
        email_key = f"failed_login_email:{email}"

        self._redis_delete(ip_key)
        self._redis_delete(email_key)

        await self.log_security_event(
            SecurityEventType.SUCCESSFUL_LOGIN,
            SecurityLevel.LOW,
            request,
            user_id=user_id,
            email=email,
            details={"cleared_failed_attempts": True}
        )

    async def check_suspicious_activity(
        self,
        request: Request,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        ip_address, user_agent = self.get_client_info(request)

        ip_activity_key = f"ip_activity:{ip_address}"
        ip_activity = self._redis_get_int(ip_activity_key)

        user_agent_suspicious = False
        if user_id:
            ua_key = f"user_agent:{user_id}"
            stored_ua = self._redis_get_str(ua_key)
            if stored_ua and stored_ua != user_agent:
                user_agent_suspicious = True
            self._redis_set(ua_key, user_agent, ex=24*3600)

        is_suspicious = (
            ip_activity > self.suspicious_threshold or
            user_agent_suspicious
        )

        if is_suspicious:
            await self.log_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                SecurityLevel.MEDIUM,
                request,
                user_id=user_id,
                details={
                    "ip_activity_count": ip_activity,
                    "user_agent_changed": user_agent_suspicious,
                    "threshold": self.suspicious_threshold
                }
            )

        return {
            "is_suspicious": is_suspicious,
            "ip_activity": ip_activity,
            "user_agent_suspicious": user_agent_suspicious
        }

    async def get_security_events(
        self,
        limit: int = 100,
        event_type: Optional[SecurityEventType] = None,
        level: Optional[SecurityLevel] = None,
        hours: int = 24
    ) -> List[SecurityEvent]:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

            keys = self._redis_keys("security_event:*")
            events = []

            for key in keys:
                data_str = self._redis_get_str(key)
                if data_str:
                    try:
                        data = json.loads(data_str)
                        event = SecurityEvent.from_dict(data)

                        if event.timestamp < cutoff:
                            continue

                        if event_type and event.event_type != event_type:
                            continue
                        if level and event.level != level:
                            continue

                        events.append(event)
                    except Exception as e:
                        logger.error(f"Failed to parse security event {key}: {e}")

            events.sort(key=lambda x: x.timestamp, reverse=True)
            return events[:limit]

        except Exception as e:
            logger.error(f"Failed to retrieve security events: {e}")
            return []

    async def get_ip_reputation(self, ip_address: str) -> Dict[str, Any]:
        failed_key = f"failed_login_ip:{ip_address}"
        failed_attempts = self._redis_get_int(failed_key)

        activity_key = f"ip_activity:{ip_address}"
        total_activity = self._redis_get_int(activity_key)

        reputation_score = 100
        if failed_attempts > 0:
            reputation_score -= failed_attempts * 10
        if total_activity > self.suspicious_threshold:
            reputation_score -= 20

        reputation_score = max(0, reputation_score)

        return {
            "ip_address": ip_address,
            "reputation_score": reputation_score,
            "failed_attempts": failed_attempts,
            "total_activity": total_activity,
            "is_trusted": reputation_score >= 80,
            "is_suspicious": reputation_score < 50
        }

    def _redis_set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        if not self.redis:
            logger.warning("Redis client not available")
            return

        try:
            if ex:
                self.redis.setex(key, ex, value)
            else:
                self.redis.set(key, value)
        except Exception as e:
            logger.error(f"Redis SET failed for {key}: {e}")

    def _redis_get_str(self, key: str) -> Optional[str]:
        if not self.redis:
            logger.warning("Redis client not available")
            return None

        try:
            result = self.redis.get(key)
            if result is None:
                return None
            if hasattr(result, 'decode'):
                return result.decode('utf-8')  # type: ignore
            return str(result)
        except Exception as e:
            logger.error(f"Redis GET failed for {key}: {e}")
            return None

    def _redis_get_int(self, key: str) -> int:
        value = self._redis_get_str(key)
        return int(value) if value else 0

    def _redis_incr(self, key: str, ttl: int) -> int:
        if not self.redis:
            logger.warning("Redis client not available")
            return 0

        try:
            result = self.redis.incr(key)
            if result == 1:
                self.redis.expire(key, ttl)
            if hasattr(result, '__int__'):
                return int(result)  # type: ignore
            elif isinstance(result, (int, str)):
                return int(result)
            else:
                    return 1
        except Exception as e:
            logger.error(f"Redis INCR failed for {key}: {e}")
            return 0

    def _redis_delete(self, key: str) -> None:
        if not self.redis:
            logger.warning("Redis client not available")
            return

        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis DELETE failed for {key}: {e}")

    def _redis_keys(self, pattern: str) -> List[str]:
        if not self.redis:
            logger.warning("Redis client not available")
            return []

        try:
            result = self.redis.keys(pattern)
            if not result:
                return []

            keys_list = []
            for item in result:  # type: ignore
                if hasattr(item, 'decode'):
                    keys_list.append(item.decode('utf-8'))  # type: ignore
                else:
                    keys_list.append(str(item))
            return keys_list
        except Exception as e:
            logger.error(f"Redis KEYS failed for {pattern}: {e}")
            return []

    def _track_ip_activity(self, ip_address: str, event: SecurityEvent) -> None:
        activity_key = f"ip_activity:{ip_address}"
        self._redis_incr(activity_key, 3600)

    def _track_user_activity(self, user_id: int, event: SecurityEvent) -> None:
        activity_key = f"user_activity:{user_id}"
        self._redis_incr(activity_key, 3600)
