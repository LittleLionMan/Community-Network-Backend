from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import HTMLResponse

from app.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.auth import verify_password
from app.services.auth import AuthService
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse, TokenRefresh,
    EmailVerification, PasswordReset, PasswordResetConfirm, EmailUpdate, ResendVerification, PasswordUpdate
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
        400: {"model": ErrorResponse, "description": "Email or display name already exists"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
    }
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        user = await auth_service.register_user(user_data)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
    }
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    user = await auth_service.authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email not verified. Please check your email and verify your account.",
            headers={"X-User-Email": user.email}
    )

    tokens = await auth_service.create_tokens(user)
    return tokens

@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid refresh token"}
    }
)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        tokens = await auth_service.refresh_access_token(token_data.refresh_token)
        return tokens
    except HTTPException:
        raise

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def logout(
    refresh_token_data: TokenRefresh,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    await auth_service.revoke_refresh_token(current_user.id, refresh_token_data.refresh_token)

@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def logout_all(
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    await auth_service.revoke_all_user_tokens(current_user.id)

@router.get(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    }
)
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    verification_data = EmailVerification(token=token)

    auth_service = AuthService(db)

    try:
        success = await auth_service.verify_email(verification_data.token)
        if success:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>E-Mail bestätigt</title>
                <meta charset="UTF-8">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
                    .success { color: green; }
                    .container { max-width: 500px; margin: 0 auto; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="success">✅ E-Mail erfolgreich bestätigt!</h1>
                    <p>Ihre E-Mail-Adresse wurde erfolgreich verifiziert.</p>
                    <p>Sie können sich jetzt anmelden.</p>
                    <p><a href="http://localhost:3000/auth/login">Zur Anmeldung</a></p>
                </div>
            </body>
            </html>
            """)
        else:
            return HTMLResponse("""
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
            """, status_code=400)
    except HTTPException as e:
        return HTMLResponse(f"""
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
        """, status_code=e.status_code)

@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
    }
)
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    email_data: ResendVerification,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    result = await db.execute(select(User).where(User.email == email_data.email))
    user = result.scalar_one_or_none()

    if user and not user.email_verified and user.is_active:
        await auth_service._send_verification_email(user)

    return {"message": "If the email exists and is unverified, a verification email has been sent"}

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
    }
)
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    reset_data: PasswordReset,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    await auth_service.request_password_reset(reset_data.email)

    return {"message": "If the email exists, a reset link has been sent"}

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    }
)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        success = await auth_service.reset_password(reset_data.token, reset_data.new_password)
        if success:
            return {"message": "Password reset successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset failed"
            )
    except HTTPException:
        raise

@router.put(
    "/email",
    response_model=UserPrivate,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid password"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        409: {"model": ErrorResponse, "description": "Email already in use"},
        422: {"model": ErrorResponse, "description": "Invalid email format"}
    }
)
async def update_email(
    email_data: EmailUpdate,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        if not verify_password(email_data.password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        if not "@" in email_data.new_email or "." not in email_data.new_email.split("@")[1]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid email format"
            )

        result = await db.execute(
            select(User).where(User.email == email_data.new_email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address already in use"
            )

        await auth_service.update_email(current_user, email_data.new_email, email_data.password)
        await db.refresh(current_user)

        return current_user

    except HTTPException:

        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email update failed"
        )

@router.put(
    "/password",
    response_model=dict,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid current password"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
    }
)
@limiter.limit("5/hour")
async def update_password(
    request: Request,
    password_data: PasswordUpdate,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        if not verify_password(password_data.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        success = await auth_service.update_user_password(current_user.id, password_data.new_password)

        if success:
            return {"message": "Password updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password update failed"
        )

@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def delete_account(
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    await auth_service.delete_user_account(current_user)

@router.get(
    "/me",
    response_model=UserPrivate,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def get_current_user_info(
    current_user = Depends(get_current_active_user)
):
    return current_user

@router.get(
    "/status",
    status_code=status.HTTP_200_OK
)
async def auth_status():
    return {
        "status": "operational",
        "features": {
            "registration": True,
            "email_verification": True,
            "password_reset": True,
            "refresh_tokens": True,
            "rate_limiting": True
        }
    }

@router.post(
    "/check-availability",
    responses={
        200: {"description": "Availability checked"},
        422: {"model": ErrorResponse, "description": "Validation error"}
    }
)
@limiter.limit("30/minute")
async def check_availability(
    request: Request,
    availability_data: dict,
    db: AsyncSession = Depends(get_db)
):
    email = availability_data.get("email")
    display_name = availability_data.get("display_name")

    if not email and not display_name:
        return {"available": True}

    if email:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            return {"available": False, "message": "E-Mail bereits vergeben"}

    if display_name:
        result = await db.execute(
            select(User).where(User.display_name == display_name)
        )
        if result.scalar_one_or_none():
            return {"available": False, "message": "Display Name bereits vergeben"}

    return {"available": True}
