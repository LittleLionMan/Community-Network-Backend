from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import HTMLResponse
from typing import Annotated

from app.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.auth import verify_password, FRONTEND_URL
from app.services.auth import AuthService
from app.core.logging import SecurityLogger, rate_limiter, get_client_ip
from app.schemas.auth import (
    AvailabilityCheck,
    ResendVerification,
    UserRegister,
    UserLogin,
    TokenResponse,
    TokenRefresh,
    EmailVerification,
    PasswordReset,
    PasswordResetConfirm,
    EmailUpdate,
    PasswordUpdate,
)
from app.schemas.user import UserPrivate
from app.schemas.common import ErrorResponse
from ..models.user import User

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["authentication"])


@router.post(
    "/register",
    response_model=UserPrivate,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Email or display name already exists",
        },
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user_data: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPrivate:
    auth_service = AuthService(db)
    client_ip = get_client_ip(request)

    try:
        rate_check = rate_limiter.check_and_record_attempt(
            f"register:{client_ip}", max_attempts=5, window_seconds=3600
        )

        if not rate_check["allowed"]:
            SecurityLogger.log_rate_limit_exceeded(
                request, "registration", details=rate_check
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many registration attempts. Try again in {rate_check['retry_after']} seconds.",
            )

        user = await auth_service.register_user(user_data)

        SecurityLogger.log_registration(
            request,
            email=user.email,
            user_id=user.id,
            success=True,
            display_name=user.display_name,
        )

        return UserPrivate.model_validate(user)

    except HTTPException:
        SecurityLogger.log_registration(
            request,
            email=user_data.email,
            success=False,
            failure_reason="validation_error",
        )
        raise
    except Exception as e:
        SecurityLogger.log_registration(
            request,
            email=user_data.email,
            success=False,
            failure_reason=f"internal_error: {str(e)}",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "Account inactive"},
        423: {"model": ErrorResponse, "description": "Account temporarily locked"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    login_data: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)
    client_ip = get_client_ip(request)

    rate_check = rate_limiter.check_and_record_attempt(
        f"login:{client_ip}:{login_data.email}",
        max_attempts=5,
        window_seconds=900,
        lockout_seconds=1800,
    )

    if not rate_check["allowed"]:
        SecurityLogger.log_rate_limit_exceeded(
            request,
            "login",
            details={
                "email": login_data.email,
                "reason": rate_check["reason"],
                "retry_after": rate_check["retry_after"],
            },
        )

        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account temporarily locked due to too many failed attempts. Try again in {rate_check['retry_after']} seconds.",
            headers={
                "Retry-After": str(rate_check["retry_after"]),
                "X-Lockout-Reason": "failed_attempts",
            },
        )

    user = await auth_service.authenticate_user(login_data.email, login_data.password)

    if not user:
        SecurityLogger.log_login_attempt(
            request,
            email=login_data.email,
            success=False,
            failure_reason="invalid_credentials",
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        SecurityLogger.log_login_attempt(
            request,
            email=login_data.email,
            success=False,
            user_id=user.id,
            failure_reason="account_inactive",
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )

    if not user.email_verified:
        SecurityLogger.log_login_attempt(
            request,
            email=login_data.email,
            success=False,
            user_id=user.id,
            failure_reason="email_not_verified",
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email not verified. Please check your email and verify your account.",
            headers={"X-User-Email": user.email},
        )

    SecurityLogger.log_login_attempt(
        request, email=user.email, success=True, user_id=user.id
    )

    tokens = await auth_service.create_tokens(user)

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=1800,
        path="/",
    )

    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=2592000,
        path="/api/auth",
    )

    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse, "description": "Invalid refresh token"}},
)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: str | None = Cookie(None),
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token"
        )

    auth_service = AuthService(db)

    try:
        tokens = await auth_service.refresh_access_token(refresh_token)

        response.set_cookie(
            key="access_token",
            value=tokens.access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=1800,
            path="/",
        )

        response.set_cookie(
            key="refresh_token",
            value=tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=2592000,
            path="/api/auth",
        )

        SecurityLogger.log_suspicious_activity(
            request, "token_refresh_success", details={"action": "token_refresh"}
        )

        return tokens
    except HTTPException as e:
        SecurityLogger.log_suspicious_activity(
            request,
            "token_refresh_failed",
            details={"action": "failed_token_refresh", "error": str(e.detail)},
        )
        raise


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def logout(
    request: Request,
    response: Response,
    refresh_token_data: TokenRefresh,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: str | None = Cookie(None),
):
    auth_service = AuthService(db)

    if refresh_token:
        await auth_service.revoke_refresh_token(current_user.id, refresh_token)

    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/auth")

    SecurityLogger.log_login_attempt(
        request,
        email=current_user.email,
        success=True,
        user_id=current_user.id,
        additional_data={"action": "user_logout"},
    )


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def logout_all(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)
    revoked_count = await auth_service.revoke_all_user_tokens(current_user.id)

    SecurityLogger.log_login_attempt(
        request,
        email=current_user.email,
        success=True,
        user_id=current_user.id,
        additional_data={
            "action": "logout_all_devices",
            "tokens_revoked": revoked_count,
        },
    )


@router.get(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    },
)
@limiter.limit("10/minute")
async def verify_email_get(
    request: Request, token: str, db: Annotated[AsyncSession, Depends(get_db)]
):
    verification_data = EmailVerification(token=token)
    auth_service = AuthService(db)

    try:
        success = await auth_service.verify_email(verification_data.token)

        if success:
            SecurityLogger.log_suspicious_activity(
                request,
                "email_verification_success",
                details={"action": "email_verified"},
            )

            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>E-Mail bestätigt</title>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }}
                    .success {{ color: green; }}
                    .container {{ max-width: 500px; margin: 0 auto; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="success">✅ E-Mail erfolgreich bestätigt!</h1>
                    <p>Ihre E-Mail-Adresse wurde erfolgreich verifiziert.</p>
                    <p>Sie können sich jetzt anmelden.</p>
                    <p><a href="{FRONTEND_URL}/auth/login">Zur Anmeldung</a></p>
                </div>
            </body>
            </html>
            """)
        else:
            SecurityLogger.log_suspicious_activity(
                request,
                "email_verification_failed",
                details={
                    "action": "email_verification_failed",
                    "reason": "invalid_token",
                },
            )

            return HTMLResponse(
                """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Verifizierung fehlgeschlagen</title>
                <meta charset="UTF-8">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
                    .error { color: red; }
                    .container { max-width: 500px; margin: 0 auto; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="error">❌ Verifizierung fehlgeschlagen</h1>
                    <p>Der Verifizierungslink ist ungültig oder abgelaufen.</p>
                    <p>Bitte fordern Sie einen neuen Link an.</p>
                </div>
            </body>
            </html>
            """,
                status_code=400,
            )
    except HTTPException as e:
        SecurityLogger.log_suspicious_activity(
            request,
            "email_verification_error",
            details={"action": "email_verification_error", "error": str(e.detail)},
        )
        return HTMLResponse(
            f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Fehler</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }}
                .error {{ color: red; }}
                .container {{ max-width: 500px; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="error">❌ Fehler</h1>
                <p>{e.detail}</p>
            </div>
        </body>
        </html>
        """,
            status_code=e.status_code,
        )


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    },
)
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    verification_data: EmailVerification,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)

    try:
        success = await auth_service.verify_email(verification_data.token)

        if success:
            SecurityLogger.log_suspicious_activity(
                request,
                "email_verification_success",
                details={"action": "email_verified"},
            )

            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>E-Mail bestätigt</title>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }}
                    .success {{ color: green; }}
                    .container {{ max-width: 500px; margin: 0 auto; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="success">✅ E-Mail erfolgreich bestätigt!</h1>
                    <p>Ihre E-Mail-Adresse wurde erfolgreich verifiziert.</p>
                    <p>Sie können sich jetzt anmelden.</p>
                    <p><a href="{FRONTEND_URL}/auth/login">Zur Anmeldung</a></p>
                </div>
            </body>
            </html>
            """)
        else:
            SecurityLogger.log_suspicious_activity(
                request,
                "email_verification_failed",
                details={
                    "action": "email_verification_failed",
                    "reason": "invalid_token",
                },
            )

            return HTMLResponse(
                """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Verifizierung fehlgeschlagen</title>
                <meta charset="UTF-8">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
                    .error { color: red; }
                    .container { max-width: 500px; margin: 0 auto; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="error">❌ Verifizierung fehlgeschlagen</h1>
                    <p>Der Verifizierungslink ist ungültig oder abgelaufen.</p>
                    <p>Bitte fordern Sie einen neuen Link an.</p>
                </div>
            </body>
            </html>
            """,
                status_code=400,
            )
    except HTTPException as e:
        SecurityLogger.log_suspicious_activity(
            request,
            "email_verification_error",
            details={"action": "email_verification_error", "error": str(e.detail)},
        )
        return HTMLResponse(
            f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Fehler</title>
            <meta charset="UTF-8">
        </head>
        <body>
            <h1>Fehler</h1>
            <p>{e.detail}</p>
        </body>
        </html>
        """,
            status_code=e.status_code,
        )


@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    email_data: ResendVerification,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)

    result = await db.execute(select(User).where(User.email == email_data.email))
    user = result.scalar_one_or_none()

    if not user:
        return {"message": "If the email exists, a verification link has been sent"}

    if user.email_verified:
        return {"message": "Email is already verified"}

    await auth_service._send_verification_email(user)

    SecurityLogger.log_suspicious_activity(
        request,
        "verification_email_resent",
        details={"email": email_data.email},
    )

    return {"message": "Verification email sent"}


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    responses={429: {"model": ErrorResponse, "description": "Rate limit exceeded"}},
)
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    reset_data: PasswordReset,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)

    SecurityLogger.log_password_reset(request, email=reset_data.email, step="requested")

    _ = await auth_service.request_password_reset(reset_data.email)
    return {"message": "If the email exists, a reset link has been sent"}


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    },
)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    reset_data: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)

    try:
        success = await auth_service.reset_password(
            reset_data.token, reset_data.new_password
        )

        if success:
            SecurityLogger.log_password_reset(
                request, email="unknown", step="completed"
            )
            return {"message": "Password reset successfully"}
        else:
            SecurityLogger.log_password_reset(
                request,
                email="unknown",
                step="failed",
                additional_data={"reason": "invalid_token"},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset failed"
            )
    except HTTPException:
        raise


@router.put(
    "/email",
    responses={
        501: {
            "model": ErrorResponse,
            "description": "Email changes require admin approval",
        }
    },
)
async def update_email(
    request: Request,
    email_data: EmailUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    SecurityLogger.log_suspicious_activity(
        request,
        "deprecated_email_change_attempt",
        user_id=current_user.id,
        email=current_user.email,
        details={
            "attempted_new_email": email_data.new_email,
            "action": "deprecated_endpoint_used",
        },
    )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "E-Mail-Änderungen erfordern Admin-Genehmigung",
            "contact": "Wenden Sie sich an support@community.de für E-Mail-Änderungen",
            "reason": "security_policy",
        },
    )


@router.put(
    "/password",
    response_model=dict,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid current password"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/hour")
async def update_password(
    request: Request,
    password_data: PasswordUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)

    try:
        if not verify_password(
            password_data.current_password, current_user.password_hash
        ):
            SecurityLogger.log_suspicious_activity(
                request,
                "password_change_failed",
                user_id=current_user.id,
                email=current_user.email,
                details={"reason": "invalid_current_password"},
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        success = await auth_service.update_user_password(
            current_user.id, password_data.new_password
        )

        if success:
            SecurityLogger.log_password_reset(
                request,
                email=current_user.email,
                step="completed",
                user_id=current_user.id,
                additional_data={"action": "password_changed_by_user"},
            )

            return {"message": "Password updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password",
            )

    except HTTPException:
        raise
    except Exception as e:
        SecurityLogger.log_suspicious_activity(
            request,
            "password_change_error",
            user_id=current_user.id,
            email=current_user.email,
            details={"error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password update failed",
        )


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def delete_account(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth_service = AuthService(db)

    SecurityLogger.log_suspicious_activity(
        request,
        "account_deletion",
        user_id=current_user.id,
        email=current_user.email,
        details={"action": "account_deleted"},
    )

    _ = await auth_service.delete_user_account(current_user)


@router.get(
    "/me",
    response_model=UserPrivate,
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user


@router.get("/status", status_code=status.HTTP_200_OK)
async def auth_status():
    return {
        "status": "operational",
        "features": {
            "registration": True,
            "email_verification": True,
            "password_reset": True,
            "refresh_tokens": True,
            "rate_limiting": True,
            "security_monitoring": True,
            "structured_logging": True,
            "failed_login_protection": True,
            "token_rotation": True,
        },
    }


@router.post(
    "/check-availability",
    responses={
        200: {"description": "Availability checked"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
@limiter.limit("30/minute")
async def check_availability(
    request: Request,
    availability_data: AvailabilityCheck,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    email = availability_data.email
    display_name = availability_data.display_name

    if not email and not display_name:
        return {"available": True}

    if email:
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            return {"available": False, "message": "E-Mail bereits vergeben"}

    if display_name:
        result = await db.execute(select(User).where(User.display_name == display_name))
        if result.scalar_one_or_none():
            return {"available": False, "message": "Display Name bereits vergeben"}

    return {"available": True}
