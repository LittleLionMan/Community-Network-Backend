from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status
from ..models.user import User
from ..models.auth import RefreshToken, EmailVerificationToken, PasswordResetToken
from ..schemas.auth import UserRegister, TokenResponse
from ..core.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    hash_token,
    send_email,
    generate_verification_email,
    generate_password_reset_email,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


class AuthService:
    db: AsyncSession

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_user(self, user_data: UserRegister) -> User:
        result = await self.db.execute(
            select(User).where(
                (User.email == user_data.email)
                | (User.display_name == user_data.display_name)
            )
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.email == user_data.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Display name already taken",
                )

        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            display_name=user_data.display_name,
            email=user_data.email,
            password_hash=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email_verified=False,
            is_active=True,
            is_admin=False,
        )

        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)

        await self._send_verification_email(db_user)

        return db_user

    async def authenticate_user(self, email: str, password: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            return None
        return user

    async def create_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(data={"sub": str(user.id)})

        refresh_token = create_refresh_token()
        refresh_token_hash = hash_token(refresh_token)

        db_refresh_token = RefreshToken(
            token_hash=refresh_token_hash,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False,
        )
        self.db.add(db_refresh_token)
        await self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        refresh_token_hash = hash_token(refresh_token)

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == refresh_token_hash,
                RefreshToken.is_revoked == False,
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
        )
        db_refresh_token = result.scalar_one_or_none()

        if not db_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        result = await self.db.execute(
            select(User).where(User.id == db_refresh_token.user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        _ = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == db_refresh_token.id)
            .values(is_revoked=True)
        )

        try:
            new_tokens = await self.create_tokens(user)
            await self.db.commit()

            return new_tokens

        except Exception:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token refresh failed",
            )

    async def revoke_refresh_token(self, user_id: int, refresh_token: str) -> bool:
        refresh_token_hash = hash_token(refresh_token)

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == refresh_token_hash,
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked == False,
            )
        )
        db_refresh_token = result.scalar_one_or_none()

        if db_refresh_token:
            _ = await self.db.execute(
                update(RefreshToken)
                .where(RefreshToken.id == db_refresh_token.id)
                .values(is_revoked=True)
            )
            await self.db.commit()
            return True
        return False

    async def revoke_all_user_tokens(self, user_id: int) -> int:
        result = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False)
            .values(is_revoked=True)
        )
        await self.db.commit()

        count = result.rowcount
        return count

    async def cleanup_expired_tokens(self) -> int:
        result = await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.expires_at < datetime.now(timezone.utc),
                RefreshToken.is_revoked == False,
            )
            .values(is_revoked=True)
        )
        await self.db.commit()

        count = result.rowcount
        return count

    async def verify_email(self, token: str) -> bool:
        token_hash = hash_token(token)

        result = await self.db.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.is_used == False,
                EmailVerificationToken.expires_at > datetime.now(timezone.utc),
            )
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token",
            )

        result = await self.db.execute(select(User).where(User.id == db_token.user_id))
        user = result.scalar_one_or_none()

        if user:
            user.email_verified = True
            user.email_verified_at = datetime.now(timezone.utc)

            _ = await self.db.execute(
                update(EmailVerificationToken)
                .where(EmailVerificationToken.id == db_token.id)
                .values(is_used=True)
            )

            await self.db.commit()
            return True

        return False

    async def request_password_reset(self, email: str) -> bool:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return True

        reset_token = create_refresh_token()
        token_hash = hash_token(reset_token)

        db_token = PasswordResetToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.db.add(db_token)
        await self.db.commit()

        email_body = generate_password_reset_email(reset_token)
        send_email(email, "Passwort zurücksetzen", email_body, is_html=True)

        return True

    async def reset_password(self, token: str, new_password: str) -> bool:
        token_hash = hash_token(token)

        result = await self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.is_used == False,
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
            )
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )

        result = await self.db.execute(select(User).where(User.id == db_token.user_id))
        user = result.scalar_one_or_none()

        if user:
            user.password_hash = get_password_hash(new_password)

            _ = await self.db.execute(
                update(PasswordResetToken)
                .where(PasswordResetToken.id == db_token.id)
                .values(is_used=True)
            )

            _ = await self.revoke_all_user_tokens(user.id)
            await self.db.commit()

            return True

        return False

    async def update_email(self, user: User, new_email: str, password: str) -> bool:
        try:
            if not verify_password(password, user.password_hash):
                raise ValueError("Invalid password")

            user.email = new_email
            user.email_verified = False
            user.email_verified_at = None

            await self.db.commit()

            await self._send_verification_email(user)

            return True

        except Exception as e:
            await self.db.rollback()
            raise e

    async def delete_user_account(self, user: User) -> bool:
        _ = await self.revoke_all_user_tokens(user.id)

        user.is_active = False
        user.email = f"deleted_{user.id}@deleted.local"
        user.display_name = f"deleted_user_{user.id}"

        await self.db.commit()
        return True

    async def _send_verification_email(self, user: User):
        verification_token = create_refresh_token()
        token_hash = hash_token(verification_token)

        db_token = EmailVerificationToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self.db.add(db_token)
        await self.db.commit()

        email_body = generate_verification_email(verification_token)
        send_email(user.email, "E-Mail-Adresse bestätigen", email_body, is_html=True)

    async def update_user_password(self, user_id: int, new_password: str) -> bool:
        try:
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                return False

            user.password_hash = get_password_hash(new_password)

            _ = await self.revoke_all_user_tokens(user_id)
            await self.db.commit()
            await self.db.refresh(user)
            return True

        except Exception as e:
            await self.db.rollback()
            raise e
