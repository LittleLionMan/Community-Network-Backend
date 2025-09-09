from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import time
import logging
from .rate_limiting import AdvancedRateLimiter
from ..database import redis_client
from ..config import settings

advanced_limiter = AdvancedRateLimiter(redis_client)

def get_rate_limit_key(request: Request):
    if not settings.DEBUG or settings.ENVIRONMENT == 'production':
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip", "") or
            request.client.host if request.client else "127.0.0.1"
        )
        return client_ip
    else:
        return get_remote_address(request)

limiter = Limiter(key_func=get_rate_limit_key)

def setup_middleware(app: FastAPI):
    cors_origins = settings.BACKEND_CORS_ORIGINS
    if settings.is_production:
        cors_origins = [origin for origin in cors_origins if not origin.startswith('http://localhost')]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) #type: ignore
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        if settings.is_production:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        response.headers.pop("server", None)

        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)

        if process_time > 1.0:  # More than 1 second
            logging.warning(f"Slow request: {request.method} {request.url} took {process_time:.2f}s")

        return response

    @app.middleware("http")
    async def advanced_rate_limiting(request: Request, call_next):
        if request.url.path in ["/health", "/api/stats"]:
            return await call_next(request)

        if request.url.path.startswith("/uploads/"):
            return await call_next(request)

        user_id = None
        try:
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                from ..core.auth import verify_token
                token = auth_header.split(" ")[1]
                payload = verify_token(token)
                if payload:
                    user_id = int(payload.get("sub", 0))
        except:
            pass

        identifier = advanced_limiter.get_identifier(request, user_id)

        if request.url.path.startswith("/api/auth/"):
            rate_check = await advanced_limiter.check_rate_limit(
                f"auth:{identifier}",
                limit=10,
                window=300,  # 5 minutes
                burst_limit=5
            )
        elif request.method in ["POST", "PUT", "DELETE"]:
            rate_check = await advanced_limiter.check_rate_limit(
                f"write:{identifier}",
                limit=100,
                window=60,
                burst_limit=20
            )
        else:
            rate_check = await advanced_limiter.check_rate_limit(
                f"read:{identifier}",
                limit=200,
                window=60
            )

        if not rate_check['allowed']:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "reason": rate_check['reason'],
                    "retry_after": int(rate_check['reset_time'] - time.time())
                },
                headers={
                    "Retry-After": str(int(rate_check['reset_time'] - time.time())),
                    "X-RateLimit-Remaining": str(rate_check['remaining']),
                    "X-RateLimit-Reset": str(int(rate_check['reset_time']))
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(rate_check['remaining'])
        response.headers["X-RateLimit-Reset"] = str(int(rate_check['reset_time']))

        return response
