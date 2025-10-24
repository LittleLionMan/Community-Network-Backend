from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from .auth import verify_token
from ..models.user import User
from ..services.event_service import EventService
from ..services.matching_service import ServiceMatchingService
from ..services.moderation_service import ModerationService
from ..services.voting_service import VotingService
from ..services.message_service import MessageService
from app.models.message import ConversationParticipant
from typing import Annotated

security = HTTPBearer()

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    access_token: str | None = Cookie(None), db: AsyncSession = Depends(get_db)
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    payload = verify_token(access_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, (str, int)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return current_user


async def get_current_admin_user(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


async def get_optional_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
    ],
    db: DatabaseSession,
) -> User | None:
    if not credentials:
        return None

    try:
        payload = verify_token(credentials.credentials, token_type="access")
        if payload is None:
            return None

        user_id = payload.get("sub")
        if user_id is None:
            return None

        if not isinstance(user_id, (str, int)):
            return None

        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            return None

        result = await db.execute(select(User).where(User.id == int(user_id_int)))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None

        return user
    except ():
        return None


async def get_event_service(db: DatabaseSession) -> EventService:
    return EventService(db)


async def get_matching_service(db: DatabaseSession) -> ServiceMatchingService:
    return ServiceMatchingService(db)


async def get_moderation_service(db: DatabaseSession) -> ModerationService:
    return ModerationService(db)


async def get_voting_service(db: DatabaseSession) -> VotingService:
    return VotingService(db)


async def get_message_service(db: DatabaseSession) -> MessageService:
    return MessageService(db)


async def verify_message_permissions(current_user: CurrentUser) -> User:
    if not current_user.messages_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Direct messages are disabled for your account",
        )
    return current_user


async def verify_conversation_participant(
    conversation_id: int, current_user: CurrentUser, db: DatabaseSession
) -> User:
    result = await db.execute(
        select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )
    return current_user
