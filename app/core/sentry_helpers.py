# aktuell nicht integriert

import sentry_sdk
from fastapi import Request
from typing import Any


def set_user_context(
    user_id: int, email: str | None = None, username: str | None = None
):
    sentry_sdk.set_user(
        {
            "id": user_id,
            "email": email,
            "username": username,
        }
    )


def set_request_context(request: Request):
    sentry_sdk.set_context(
        "request",
        {
            "url": str(request.url),
            "method": request.method,
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
        },
    )


def capture_exception_with_context(
    error: Exception, context: dict[str, Any] | None = None, level: str = "error"
):
    if context:
        for key, value in context.items():
            sentry_sdk.set_context(key, value)

    sentry_sdk.capture_exception(error, level=level)


def capture_message(
    message: str,
    context: dict[str, Any] | None = None,
    level: str = "info",
):
    if context:
        for key, value in context.items():
            sentry_sdk.set_context(key, value)

    sentry_sdk.capture_message(message, level=level)


def add_breadcrumb(
    message: str,
    category: str = "default",
    level: str = "info",
    data: dict[str, Any] | None = None,
):
    sentry_sdk.add_breadcrumb(
        message=message, category=category, level=level, data=data or {}
    )
