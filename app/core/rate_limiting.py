import time
import redis.asyncio as redis
from typing import cast
from fastapi import Request
import hashlib

class AdvancedRateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis: redis.Redis = redis_client
        self.local_cache: dict[str, dict[str, object]] = {}
        self.cache_ttl: int = 60

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window: int = 60,
        burst_limit: int | None = None
    ) -> dict[str, object]:
        current_time = time.time()
        key = f"rate_limit:{identifier}:{window}"

        try:
            pipe = self.redis.pipeline()
            _ = pipe.get(key)
            _ = pipe.ttl(key)
            redis_result = await pipe.execute()

            current_count = int(redis_result[0] or 0)
            ttl = cast(int, redis_result[1])

            if ttl == -1:
                await self.redis.expire(key, window)
                ttl = window

            if burst_limit and current_count >= burst_limit:
                return {
                    'allowed': False,
                    'remaining': 0,
                    'reset_time': current_time + ttl,
                    'reason': 'burst_limit_exceeded'
                }

            if current_count >= limit:
                return {
                    'allowed': False,
                    'remaining': 0,
                    'reset_time': current_time + ttl,
                    'reason': 'rate_limit_exceeded'
                }

            if current_count == 0:
                await self.redis.setex(key, window, 1)
            else:
                await self.redis.incr(key)

            return {
                'allowed': True,
                'remaining': limit - current_count - 1,
                'reset_time': current_time + ttl,
                'reason': 'allowed'
            }

        except Exception as e:
            print(f"Redis rate limit failed, using local cache: {e}")
            return await self._check_rate_limit_local(identifier, limit, window, current_time)

    async def _check_rate_limit_local(
        self,
        identifier: str,
        limit: int,
        window: int,
        current_time: float
    ) -> dict[str, object]:
        key = f"{identifier}:{window}"

        if key not in self.local_cache:
            self.local_cache[key] = {'count': 0, 'reset_time': current_time + window}

        cache_entry = self.local_cache[key]
        reset_time = cast(float, cache_entry['reset_time'])
        count = cast(int, cache_entry['count'])

        if current_time >= reset_time:
            cache_entry['count'] = 0
            cache_entry['reset_time'] = current_time + window

        if count >= limit:
            return {
                'allowed': False,
                'remaining': 0,
                'reset_time': cache_entry['reset_time'],
                'reason': 'rate_limit_exceeded_local'
            }

        count += 1

        return {
            'allowed': True,
            'remaining': limit - count,
            'reset_time': reset_time,
            'reason': 'allowed_local'
        }

    def get_identifier(self, request: Request, user_id: int | None = None) -> str:
        if user_id:
            return f"user:{user_id}"

        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip", "") or
            request.client.host if request.client else "unknown"
        )

        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
        return f"ip:{ip_hash}"
