from functools import wraps
from fastapi import HTTPException, status, Request, Response
from typing import Callable, TypeVar, ParamSpec, cast
from _collections_abc import Awaitable
from .content_rate_limiter import content_rate_limiter, ContentType
from .logging import SecurityLogger
from ..models.user import User

P = ParamSpec('P')
T = TypeVar('T')

def content_rate_limit(content_type: ContentType):
    def decorator[T](func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            request = None
            current_user = None

            for key, value in kwargs.items():
                if key == 'request' and hasattr(value, 'method'):
                    request = value
                elif isinstance(value, User):
                    current_user = value
                elif hasattr(value, 'id') and hasattr(value, 'created_at'):
                    current_user = value

            for arg in args:
                if hasattr(arg, 'method') and hasattr(arg, 'url'):
                    request = arg
                elif isinstance(arg, User):
                    current_user = arg
                elif hasattr(arg, 'id') and hasattr(arg, 'created_at'):
                    current_user = arg

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required for rate limiting"
                )

            assert isinstance(current_user, User)



            user_tier = content_rate_limiter.get_user_tier(
                current_user.created_at,
                is_trusted=getattr(current_user, 'is_trusted', False)
            )

            rate_check = content_rate_limiter.check_rate_limit(
                current_user.id,
                content_type,
                user_tier
            )

            if not rate_check["allowed"]:
                if request:
                    assert isinstance(request, Request)
                    SecurityLogger.log_rate_limit_exceeded(
                        request,
                        f"content_{content_type.value}",
                        user_id=current_user.id,
                        details=rate_check
                    )

                error_detail = {
                    "error": "Rate limit exceeded",
                    "content_type": content_type.value,
                    "reason": rate_check["reason"],
                    "limit_type": rate_check["limit_type"],
                    "retry_after": rate_check["retry_after"],
                    "user_tier": user_tier.value
                }

                if "current_count" in rate_check:
                    error_detail["current_count"] = rate_check["current_count"]
                    error_detail["limit"] = rate_check["limit"]
                    error_detail["window"] = rate_check["window"]

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=error_detail,
                    headers={
                        "Retry-After": str(rate_check["retry_after"]),
                        "X-RateLimit-Type": content_type.value,
                        "X-RateLimit-Tier": user_tier.value
                    }
                )

            result = await func(*args, **kwargs)

            if hasattr(result, 'headers') and rate_check.get("remaining"):
                remaining = rate_check["remaining"]
                assert isinstance(result, Response)
                remaining = cast(dict[str, int], rate_check["remaining"])
                result.headers["X-RateLimit-Remaining-Hourly"] = str(remaining.get("hourly", 0))
                result.headers["X-RateLimit-Remaining-Daily"] = str(remaining.get("daily", 0))
                if remaining.get("weekly") is not None:
                    result.headers["X-RateLimit-Remaining-Weekly"] = str(remaining["weekly"])

            return result

        return wrapper
    return decorator

def forum_post_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.FORUM_POST)(func)

def forum_reply_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.FORUM_REPLY)(func)

def event_create_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.EVENT_CREATE)(func)

def service_create_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.SERVICE_CREATE)(func)

def message_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.PRIVATE_MESSAGE)(func)

def conversation_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.NEW_CONVERSATION)(func)

def comment_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.COMMENT)(func)

def poll_create_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.POLL_CREATE)(func)

def poll_vote_rate_limit(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    return content_rate_limit(ContentType.POLL_VOTE)(func)

class ReadRateLimiter:

    def __init__(self):
        self.attempts: dict[str, dict[str, list[tuple[float, int]]]] = {}

        self.limits: dict[str, int] = {
            "user_profile": 200,
            "user_search": 100,
            "event_listing": 300,
            "event_search": 150,
            "service_listing": 300,
            "service_search": 150,
            "forum_listing": 400,
            "message_history": 500,
            "general_api": 1000
        }

    def check_read_limit(self, ip_address: str, endpoint_type: str) -> dict[str, object]:
        import time

        now = time.time()
        hour_ago = now - 3600

        if ip_address not in self.attempts:
            self.attempts[ip_address] = {}
        if endpoint_type not in self.attempts[ip_address]:
            self.attempts[ip_address][endpoint_type] = []

        attempts = self.attempts[ip_address][endpoint_type]
        attempts[:] = [(timestamp, count) for timestamp, count in attempts if timestamp > hour_ago]

        current_count = sum(count for _timestamp, count in attempts)
        limit = self.limits.get(endpoint_type, self.limits["general_api"])

        if current_count >= limit:
            return {
                "allowed": False,
                "reason": "read_limit_exceeded",
                "current_count": current_count,
                "limit": limit,
                "retry_after": 3600 - int(now % 3600)
            }

        attempts.append((now, 1))

        return {
            "allowed": True,
            "remaining": limit - current_count - 1,
            "limit": limit
        }

read_rate_limiter = ReadRateLimiter()

def read_rate_limit(endpoint_type: str):
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            request = None
            for arg in args:
                if hasattr(arg, 'method') and hasattr(arg, 'client'):
                    request = arg
                    break

            if not request:
                for _key, value in kwargs.items():
                    if hasattr(value, 'method') and hasattr(value, 'client'):
                        request = value
                        break

            if request:
                assert isinstance(request, Request)
                from .logging import get_client_ip
                ip_address = get_client_ip(request)

                rate_check = read_rate_limiter.check_read_limit(ip_address, endpoint_type)

                if not rate_check["allowed"]:
                    SecurityLogger.log_rate_limit_exceeded(
                        request,
                        f"read_{endpoint_type}",
                        details=rate_check
                    )

                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": "Read rate limit exceeded",
                            "endpoint_type": endpoint_type,
                            "current_count": rate_check["current_count"],
                            "limit": rate_check["limit"],
                            "retry_after": rate_check["retry_after"]
                        },
                        headers={
                            "Retry-After": str(rate_check["retry_after"]),
                            "X-RateLimit-Type": f"read_{endpoint_type}"
                        }
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
