# api/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from typing import Any

from app.database import get_db
from app.core.dependencies import get_current_user, get_current_active_user
from app.services.auth import AuthService
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse, TokenRefresh,
    EmailVerification, PasswordReset, PasswordResetConfirm, EmailUpdate
)
from app.schemas.user import UserPrivate
from app.schemas.common import ErrorResponse

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
@limiter.limit("5/minute")  # 5 registrations per minute per IP
async def register(
    request: Request,
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        user = auth_service.register_user(user_data)
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
@limiter.limit("10/minute")  # 10 login attempts per minute per IP
async def login(
    request: Request,
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    # Authenticate user
    user = auth_service.authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Create tokens
    tokens = auth_service.create_tokens(user)
    return tokens

@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid refresh token"}
    }
)
@limiter.limit("20/minute")  # 20 refresh attempts per minute per IP
async def refresh_token(
    request: Request,
    token_data: TokenRefresh,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        tokens = auth_service.refresh_access_token(token_data.refresh_token)
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
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)
    auth_service.revoke_refresh_token(current_user.id, refresh_token_data.refresh_token)

@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def logout_all(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)
    auth_service.revoke_all_user_tokens(current_user.id)

@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    }
)
@limiter.limit("10/minute")  # 10 verification attempts per minute per IP
async def verify_email(
    request,
    verification_data: EmailVerification,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        success = auth_service.verify_email(verification_data.token)
        if success:
            return {"message": "Email verified successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email verification failed"
            )
    except HTTPException:
        raise

@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        409: {"model": ErrorResponse, "description": "Email already verified"}
    }
)
@limiter.limit("3/hour")  # 3 resend attempts per hour per IP
async def resend_verification(
    request: Request,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already verified"
        )

    auth_service = AuthService(db)
    auth_service._send_verification_email(current_user)

    return {"message": "Verification email sent"}

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"}
    }
)
@limiter.limit("3/hour")  # 3 password reset requests per hour per IP
async def forgot_password(
    request: Request,
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)
    auth_service.request_password_reset(reset_data.email)

    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a reset link has been sent"}

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or expired token"}
    }
)
@limiter.limit("5/minute")  # 5 reset attempts per minute per IP
async def reset_password(
    request: Request,
    reset_data: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        success = auth_service.reset_password(reset_data.token, reset_data.new_password)
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
        400: {"model": ErrorResponse, "description": "Invalid password or email already in use"},
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def update_email(
    email_data: EmailUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    try:
        auth_service.update_email(current_user, email_data.new_email, email_data.password)
        db.refresh(current_user)
        return current_user
    except HTTPException:
        raise

@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"}
    }
)
async def delete_account(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)
    auth_service.delete_user_account(current_user)

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
