from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import time
import logging
from .logging import SecurityLogger, get_client_ip
from ..config import settings

from .logging import rate_limiter as advanced_limiter

def get_rate_limit_key(request: Request):
    if not settings.DEBUG or settings.ENVIRONMENT == 'production':
        client_ip = get_client_ip(request)
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
        client_ip = get_client_ip(request)

        if await is_ip_blocked(client_ip):
            return create_blocked_response(client_ip)

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

        if process_time > 1.0:
            logging.warning(f"Slow request: {request.method} {request.url} took {process_time:.2f}s")

        return response

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        response.headers.pop("server", None)

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

        client_ip = get_client_ip(request)
        identifier = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        rate_check = {"allowed": True, "remaining": 100, "reset_time": time.time() + 60}

        if request.url.path.startswith("/api/auth/login"):
            rate_check = advanced_limiter.check_and_record_attempt(
                f"login:{identifier}",
                max_attempts=5,
                window_seconds=300,
                lockout_seconds=1800
            )
        elif request.url.path.startswith("/api/auth/register"):
            rate_check = advanced_limiter.check_and_record_attempt(
                f"register:{identifier}",
                max_attempts=3,
                window_seconds=3600,
                lockout_seconds=3600
            )
        elif request.url.path.startswith("/api/auth/"):
            rate_check = advanced_limiter.check_and_record_attempt(
                f"auth:{identifier}",
                max_attempts=20,
                window_seconds=3600
            )

        if not rate_check['allowed']:
            SecurityLogger.log_rate_limit_exceeded(
                request,
                "middleware_rate_limit",
                user_id=user_id,
                details=rate_check
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "reason": rate_check.get('reason', 'too_many_requests'),
                    "retry_after": rate_check.get('retry_after', 60)
                },
                headers={
                    "Retry-After": str(rate_check.get('retry_after', 60)),
                    "X-RateLimit-Remaining": str(rate_check.get('remaining', 0))
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(rate_check.get('remaining', 100))

        return response

    @app.middleware("http")
    async def suspicious_request_detector(request: Request, call_next):
        suspicious_indicators = []

        user_agent = request.headers.get("user-agent", "")
        if not user_agent or len(user_agent) < 10:
            suspicious_indicators.append("missing_or_short_user_agent")

        url_path = str(request.url.path).lower()
        attack_patterns = [
            "admin", "phpmyadmin", "wp-admin", ".env", "config",
            "backup", "test", "dev", "staging", "api/v1/admin"
        ]

        for pattern in attack_patterns:
            if pattern in url_path and not url_path.startswith("/api/admin/"):
                suspicious_indicators.append(f"suspicious_path_{pattern}")

        query_string = str(request.url.query).lower()
        sql_patterns = ["select", "union", "drop", "insert", "delete", "update", "script"]

        for pattern in sql_patterns:
            if pattern in query_string:
                suspicious_indicators.append(f"sql_injection_attempt_{pattern}")

        if suspicious_indicators:
            SecurityLogger.log_suspicious_activity(
                request,
                "suspicious_request_detected",
                details={
                    "indicators": suspicious_indicators,
                    "user_agent": user_agent,
                    "url_path": url_path,
                    "query_string": query_string[:200]
                }
            )

            high_risk_indicators = [
                indicator for indicator in suspicious_indicators
                if any(pattern in indicator for pattern in ["sql_injection", "admin", "config"])
            ]

            if len(high_risk_indicators) >= 2:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "Suspicious request detected",
                        "detail": "Request blocked for security reasons"
                    }
                )

        response = await call_next(request)
        return response

async def is_ip_blocked(ip_address: str) -> bool:
    blocked_ips = ["192.168.1.100"]
    return ip_address in blocked_ips

def create_blocked_response(ip_address: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "Access denied",
            "detail": "Your IP address has been temporarily blocked due to security concerns",
            "ip_address": ip_address,
            "contact": "Please contact support if you believe this is an error"
        },
        headers={
            "X-Block-Reason": "admin_action",
            "X-Block-Type": "ip_address"
        }
    )
