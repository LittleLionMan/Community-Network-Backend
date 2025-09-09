from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import time
import logging
from typing import Optional, Dict, Any
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

        if request.url.path.startswith("/api/auth/login"):
            rate_check = await advanced_limiter.check_rate_limit(
                f"login:{identifier}",
                limit=5,
                window=300,
                burst_limit=3
            )
        elif request.url.path.startswith("/api/auth/"):
            rate_check = await advanced_limiter.check_rate_limit(
                f"auth:{identifier}",
                limit=10,
                window=300,
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
            await log_rate_limit_exceeded(request, rate_check, user_id)

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
            await log_security_middleware_event(
                request,
                "suspicious_request",
                {
                    "action": "suspicious_request_detected",
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

def get_client_ip(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip", "") or
        request.client.host if request.client else "unknown"
    )

async def is_ip_blocked(ip_address: str) -> bool:
    try:
        block_key = f"blocked_ip:{ip_address}"
        blocked_data = redis_client.get(block_key)
        return blocked_data is not None
    except Exception as e:
        logging.error(f"Failed to check IP block status for {ip_address}: {e}")
        return False

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

async def log_rate_limit_exceeded(request: Request, rate_check: Dict[str, Any], user_id: Optional[int] = None):
    try:
        from ..services.security_service import SecurityService, SecurityEventType, SecurityLevel
        from ..database import get_db

        async for db in get_db():
            security_service = SecurityService(db)

            await security_service.log_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                SecurityLevel.MEDIUM,
                request,
                user_id=user_id,
                details={
                    "action": "rate_limit_exceeded",
                    "endpoint": str(request.url.path),
                    "method": request.method,
                    "rate_limit_reason": rate_check.get('reason', 'unknown'),
                    "remaining_requests": rate_check.get('remaining', 0),
                    "reset_time": rate_check.get('reset_time', 0)
                }
            )
            break

    except Exception as e:
        logging.error(f"Failed to log rate limit exceeded event: {e}")

async def log_security_middleware_event(request: Request, event_type: str, details: Dict[str, Any]):
    try:
        from ..services.security_service import SecurityService, SecurityEventType, SecurityLevel
        from ..database import get_db

        event_type_mapping = {
            "ip_blocked": SecurityEventType.ACCOUNT_LOCKED,
            "suspicious_request": SecurityEventType.SUSPICIOUS_ACTIVITY,
            "slow_request": SecurityEventType.SUSPICIOUS_ACTIVITY
        }

        security_event_type = event_type_mapping.get(event_type, SecurityEventType.SUSPICIOUS_ACTIVITY)

        async for db in get_db():
            security_service = SecurityService(db)

            await security_service.log_security_event(
                security_event_type,
                SecurityLevel.MEDIUM,
                request,
                details=details
            )
            break

    except Exception as e:
        logging.error(f"Failed to log security middleware event: {e}")
