from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from enum import Enum
from dataclasses import dataclass
import time

class ContentType(str, Enum):
    FORUM_POST = "forum_post"
    FORUM_REPLY = "forum_reply"
    EVENT_CREATE = "event_create"
    SERVICE_CREATE = "service_create"
    EVENT_REPLY = "event_reply"
    SERVICE_REPLY = "service_reply"
    PRIVATE_MESSAGE = "private_message"
    NEW_CONVERSATION = "new_conversation"
    COMMENT = "comment"
    POLL_CREATE = "poll_create"
    POLL_VOTE = "poll_vote"

class UserTier(str, Enum):
    NEW = "new"
    REGULAR = "regular"
    ESTABLISHED = "established"
    TRUSTED = "trusted"

@dataclass
class RateLimit:
    hourly_limit: int
    daily_limit: int
    weekly_limit: Optional[int] = None
    burst_limit: Optional[int] = None

class ContentRateLimiter:

    def __init__(self):
        self.attempts = {}
        self.lockouts = {}

        self.limits = self._setup_rate_limits()

    def _setup_rate_limits(self) -> Dict[ContentType, Dict[UserTier, RateLimit]]:
        return {
            ContentType.FORUM_POST: {
                UserTier.NEW: RateLimit(hourly_limit=5, daily_limit=15, burst_limit=2),
                UserTier.REGULAR: RateLimit(hourly_limit=10, daily_limit=50, burst_limit=3),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=15, daily_limit=75, burst_limit=5),
                UserTier.TRUSTED: RateLimit(hourly_limit=25, daily_limit=100, burst_limit=8)
            },
            ContentType.FORUM_REPLY: {
                UserTier.NEW: RateLimit(hourly_limit=15, daily_limit=50, burst_limit=5),
                UserTier.REGULAR: RateLimit(hourly_limit=30, daily_limit=200, burst_limit=10),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=50, daily_limit=300, burst_limit=15),
                UserTier.TRUSTED: RateLimit(hourly_limit=75, daily_limit=500, burst_limit=20)
            },
            ContentType.EVENT_CREATE: {
                UserTier.NEW: RateLimit(hourly_limit=1, daily_limit=2, weekly_limit=5, burst_limit=1),
                UserTier.REGULAR: RateLimit(hourly_limit=2, daily_limit=5, weekly_limit=20, burst_limit=1),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=3, daily_limit=8, weekly_limit=30, burst_limit=2),
                UserTier.TRUSTED: RateLimit(hourly_limit=5, daily_limit=15, weekly_limit=50, burst_limit=3)
            },
            ContentType.SERVICE_CREATE: {
                UserTier.NEW: RateLimit(hourly_limit=2, daily_limit=3, weekly_limit=10, burst_limit=1),
                UserTier.REGULAR: RateLimit(hourly_limit=3, daily_limit=8, weekly_limit=25, burst_limit=2),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=5, daily_limit=15, weekly_limit=40, burst_limit=3),
                UserTier.TRUSTED: RateLimit(hourly_limit=8, daily_limit=25, weekly_limit=60, burst_limit=4)
            },
            ContentType.EVENT_REPLY: {
                UserTier.NEW: RateLimit(hourly_limit=20, daily_limit=80, burst_limit=8),
                UserTier.REGULAR: RateLimit(hourly_limit=40, daily_limit=200, burst_limit=15),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=60, daily_limit=300, burst_limit=20),
                UserTier.TRUSTED: RateLimit(hourly_limit=100, daily_limit=500, burst_limit=30)
            },
            ContentType.SERVICE_REPLY: {
                UserTier.NEW: RateLimit(hourly_limit=20, daily_limit=80, burst_limit=8),
                UserTier.REGULAR: RateLimit(hourly_limit=40, daily_limit=200, burst_limit=15),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=60, daily_limit=300, burst_limit=20),
                UserTier.TRUSTED: RateLimit(hourly_limit=100, daily_limit=500, burst_limit=30)
            },
            ContentType.PRIVATE_MESSAGE: {
                UserTier.NEW: RateLimit(hourly_limit=30, daily_limit=100, burst_limit=10),
                UserTier.REGULAR: RateLimit(hourly_limit=75, daily_limit=300, burst_limit=20),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=150, daily_limit=600, burst_limit=30),
                UserTier.TRUSTED: RateLimit(hourly_limit=250, daily_limit=1000, burst_limit=50)
            },
            ContentType.NEW_CONVERSATION: {
                UserTier.NEW: RateLimit(hourly_limit=5, daily_limit=20, burst_limit=3),
                UserTier.REGULAR: RateLimit(hourly_limit=15, daily_limit=50, burst_limit=5),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=25, daily_limit=80, burst_limit=8),
                UserTier.TRUSTED: RateLimit(hourly_limit=40, daily_limit=120, burst_limit=12)
            },
            ContentType.COMMENT: {
                UserTier.NEW: RateLimit(hourly_limit=25, daily_limit=100, burst_limit=10),
                UserTier.REGULAR: RateLimit(hourly_limit=50, daily_limit=250, burst_limit=20),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=75, daily_limit=400, burst_limit=25),
                UserTier.TRUSTED: RateLimit(hourly_limit=120, daily_limit=600, burst_limit=40)
            },
            ContentType.POLL_CREATE: {
                UserTier.NEW: RateLimit(hourly_limit=2, daily_limit=5, weekly_limit=15, burst_limit=1),
                UserTier.REGULAR: RateLimit(hourly_limit=3, daily_limit=10, weekly_limit=30, burst_limit=2),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=5, daily_limit=15, weekly_limit=50, burst_limit=3),
                UserTier.TRUSTED: RateLimit(hourly_limit=8, daily_limit=25, weekly_limit=75, burst_limit=4)
            },
            ContentType.POLL_VOTE: {
                UserTier.NEW: RateLimit(hourly_limit=50, daily_limit=200, burst_limit=20),
                UserTier.REGULAR: RateLimit(hourly_limit=100, daily_limit=500, burst_limit=30),
                UserTier.ESTABLISHED: RateLimit(hourly_limit=150, daily_limit=750, burst_limit=40),
                UserTier.TRUSTED: RateLimit(hourly_limit=200, daily_limit=1000, burst_limit=50)
            }
        }

    def get_user_tier(self, user_created_at: datetime, is_trusted: bool = False) -> UserTier:
        if is_trusted:
            return UserTier.TRUSTED

        account_age = datetime.now(timezone.utc) - user_created_at

        if account_age < timedelta(days=7):
            return UserTier.NEW
        elif account_age < timedelta(days=30):
            return UserTier.REGULAR
        else:
            return UserTier.ESTABLISHED

    def check_rate_limit(
        self,
        user_id: int,
        content_type: ContentType,
        user_tier: UserTier
    ) -> Dict[str, Any]:

        now = time.time()
        key = f"{user_id}:{content_type.value}"

        if key in self.lockouts and now < self.lockouts[key]:
            return {
                "allowed": False,
                "reason": "locked_out",
                "retry_after": int(self.lockouts[key] - now),
                "limit_type": "lockout"
            }
        elif key in self.lockouts and now >= self.lockouts[key]:
            del self.lockouts[key]

        if content_type not in self.limits or user_tier not in self.limits[content_type]:
            rate_limit = self.limits[content_type][UserTier.REGULAR]
        else:
            rate_limit = self.limits[content_type][user_tier]

        if user_id not in self.attempts:
            self.attempts[user_id] = {}
        if content_type not in self.attempts[user_id]:
            self.attempts[user_id][content_type] = []

        attempts = self.attempts[user_id][content_type]
        hour_ago = now - 3600
        day_ago = now - 86400
        week_ago = now - 604800
        five_min_ago = now - 300

        attempts[:] = [
            (timestamp, count) for timestamp, count in attempts
            if timestamp > week_ago
        ]

        hourly_count = sum(count for timestamp, count in attempts if timestamp > hour_ago)
        daily_count = sum(count for timestamp, count in attempts if timestamp > day_ago)
        weekly_count = sum(count for timestamp, count in attempts if timestamp > week_ago)
        burst_count = sum(count for timestamp, count in attempts if timestamp > five_min_ago)

        if rate_limit.burst_limit and burst_count >= rate_limit.burst_limit:
            self.lockouts[key] = now + 300
            return {
                "allowed": False,
                "reason": "burst_limit_exceeded",
                "current_count": burst_count,
                "limit": rate_limit.burst_limit,
                "window": "5 minutes",
                "retry_after": 300,
                "limit_type": "burst"
            }

        if hourly_count >= rate_limit.hourly_limit:
            return {
                "allowed": False,
                "reason": "hourly_limit_exceeded",
                "current_count": hourly_count,
                "limit": rate_limit.hourly_limit,
                "window": "1 hour",
                "retry_after": 3600 - int(now % 3600),
                "limit_type": "hourly"
            }

        if daily_count >= rate_limit.daily_limit:
            return {
                "allowed": False,
                "reason": "daily_limit_exceeded",
                "current_count": daily_count,
                "limit": rate_limit.daily_limit,
                "window": "24 hours",
                "retry_after": 86400 - int(now % 86400),
                "limit_type": "daily"
            }

        if rate_limit.weekly_limit and weekly_count >= rate_limit.weekly_limit:
            return {
                "allowed": False,
                "reason": "weekly_limit_exceeded",
                "current_count": weekly_count,
                "limit": rate_limit.weekly_limit,
                "window": "7 days",
                "retry_after": 604800 - int(now % 604800),
                "limit_type": "weekly"
            }

        attempts.append((now, 1))

        return {
            "allowed": True,
            "remaining": {
                "hourly": rate_limit.hourly_limit - hourly_count - 1,
                "daily": rate_limit.daily_limit - daily_count - 1,
                "weekly": (rate_limit.weekly_limit - weekly_count - 1) if rate_limit.weekly_limit else None,
                "burst": (rate_limit.burst_limit - burst_count - 1) if rate_limit.burst_limit else None
            },
            "limits": {
                "hourly": rate_limit.hourly_limit,
                "daily": rate_limit.daily_limit,
                "weekly": rate_limit.weekly_limit,
                "burst": rate_limit.burst_limit
            },
            "user_tier": user_tier.value
        }

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        if user_id not in self.attempts:
            return {"usage": {}, "lockouts": {}}

        now = time.time()
        hour_ago = now - 3600
        day_ago = now - 86400

        stats = {}
        for content_type, attempts in self.attempts[user_id].items():
            hourly_count = sum(count for timestamp, count in attempts if timestamp > hour_ago)
            daily_count = sum(count for timestamp, count in attempts if timestamp > day_ago)

            stats[content_type] = {
                "hourly_usage": hourly_count,
                "daily_usage": daily_count
            }

        lockouts = {}
        for key, lockout_time in self.lockouts.items():
            if key.startswith(f"{user_id}:") and now < lockout_time:
                content_type = key.split(":", 1)[1]
                lockouts[content_type] = {
                    "locked_until": lockout_time,
                    "seconds_remaining": int(lockout_time - now)
                }

        return {
            "usage": stats,
            "lockouts": lockouts
        }

    def clear_user_limits(self, user_id: int, content_type: Optional[ContentType] = None):
        if content_type:
            if user_id in self.attempts and content_type in self.attempts[user_id]:
                del self.attempts[user_id][content_type]

            lockout_key = f"{user_id}:{content_type.value}"
            if lockout_key in self.lockouts:
                del self.lockouts[lockout_key]
        else:
            if user_id in self.attempts:
                del self.attempts[user_id]

            keys_to_remove = [key for key in self.lockouts.keys() if key.startswith(f"{user_id}:")]
            for key in keys_to_remove:
                del self.lockouts[key]

content_rate_limiter = ContentRateLimiter()
