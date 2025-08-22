# services/auth_service.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from ..models.user import User
from ..models.auth import RefreshToken, EmailVerificationToken, PasswordResetToken
from ..schemas.auth import UserRegister, TokenResponse
from ..core.auth import (
    verify_password, get_password_hash, create_access_token, create_refresh_token,
    hash_token, send_email, generate_verification_email, generate_password_reset_email,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
)

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register_user(self, user_data: UserRegister) -> User:
        existing_user = self.db.query(User).filter(
            (User.email == user_data.email) | (User.display_name == user_data.display_name)
        ).first()

        if existing_user:
            if existing_user.email == user_data.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Display name already taken"
                )

        # Create new user
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            display_name=user_data.display_name,
            email=user_data.email,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email_verified=False,
            is_active=True,
            is_admin=False
        )

        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)

        # Send verification email
        self._send_verification_email(db_user)

        return db_user

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        user = self.db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    def create_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(data={"sub": str(user.id)})

        refresh_token = create_refresh_token()
        refresh_token_hash = hash_token(refresh_token)

        db_refresh_token = RefreshToken(
            token_hash=refresh_token_hash,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        )
        self.db.add(db_refresh_token)
        self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        refresh_token_hash = hash_token(refresh_token)

        db_refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == refresh_token_hash,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc)
        ).first()

        if not db_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        user = self.db.query(User).filter(User.id == db_refresh_token.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        db_refresh_token.is_revoked = True

        new_tokens = self.create_tokens(user)
        self.db.commit()

        return new_tokens

    def revoke_refresh_token(self, user_id: int, refresh_token: str) -> bool:
        refresh_token_hash = hash_token(refresh_token)

        db_refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == refresh_token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False
        ).first()

        if db_refresh_token:
            db_refresh_token.is_revoked = True
            self.db.commit()
            return True
        return False

    def revoke_all_user_tokens(self, user_id: int) -> int:
        count = self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False
        ).update({"is_revoked": True})
        self.db.commit()
        return count

    def verify_email(self, token: str) -> bool:
        token_hash = hash_token(token)

        db_token = self.db.query(EmailVerificationToken).filter(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.is_used == False,
            EmailVerificationToken.expires_at > datetime.now(timezone.utc)
        ).first()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )

        user = self.db.query(User).filter(User.id == db_token.user_id).first()
        if user:
            user.email_verified = True
            user.email_verified_at = datetime.now(timezone.utc)

            db_token.is_used = True

            self.db.commit()
            return True

        return False

    def request_password_reset(self, email: str) -> bool:
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            return True

        reset_token = create_refresh_token()
        token_hash = hash_token(reset_token)

        db_token = PasswordResetToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)  # 1 hour expiry
        )
        self.db.add(db_token)
        self.db.commit()

        email_body = generate_password_reset_email(email, reset_token)
        send_email(email, "Passwort zurücksetzen", email_body, is_html=True)

        return True

    def reset_password(self, token: str, new_password: str) -> bool:
        token_hash = hash_token(token)

        db_token = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.is_used == False,
            PasswordResetToken.expires_at > datetime.now(timezone.utc)
        ).first()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )

        user = self.db.query(User).filter(User.id == db_token.user_id).first()
        if user:
            user.hashed_password = get_password_hash(new_password)

            db_token.is_used = True

            self.revoke_all_user_tokens(user.id)

            self.db.commit()
            return True

        return False

    def update_email(self, user: User, new_email: str, password: str) -> bool:
        if not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect password"
            )

        existing_user = self.db.query(User).filter(
            User.email == new_email,
            User.id != user.id
        ).first()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

        user.email = new_email
        user.email_verified = False
        user.email_verified_at = None
        self.db.commit()

        self._send_verification_email(user)

        return True

    def delete_user_account(self, user: User) -> bool:
        self.revoke_all_user_tokens(user.id)

        user.is_active = False
        user.email = f"deleted_{user.id}@deleted.local"
        user.display_name = f"deleted_user_{user.id}"

        self.db.commit()
        return True

    def _send_verification_email(self, user: User):
        verification_token = create_refresh_token()
        token_hash = hash_token(verification_token)

        db_token = EmailVerificationToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24)  # 24 hours expiry
        )
        self.db.add(db_token)
        self.db.commit()

        email_body = generate_verification_email(user.email, verification_token)
        send_email(user.email, "E-Mail-Adresse bestätigen", email_body, is_html=True)
