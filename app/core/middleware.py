from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from typing import Callable
from _collections_abc import Awaitable
import time
import logging
from ..config import settings

limiter = Limiter(key_func=get_remote_address)

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
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # type: ignore
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def _(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.time()

        response = await call_next(request)

        if settings.is_production:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if "server" in response.headers:
            del response.headers["server"]

        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)

        if process_time > 2.0:
            logging.warning(
                f"Slow request: {request.method} {request.url.path} " +
                f"took {process_time:.2f}s from {request.client.host if request.client else 'unknown'}"
            )

        return response
