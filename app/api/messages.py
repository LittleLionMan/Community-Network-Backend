from fastapi import APIRouter, Depends, HTTPException, status, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json
import logging
from datetime import datetime

from ..database import get_db
from ..core.dependencies import get_current_user, get_current_admin_user
from ..models.user import User
from ..services.message_service import MessageService
from ..services.websocket_service import websocket_manager
from ..schemas.message import (
    ConversationCreate, MessageCreate, MessageUpdate,
    ConversationResponse, MessageResponse, ConversationDetailResponse,
    MessageListResponse, ConversationListResponse, UnreadCountResponse,
    MessageModerationAction, ConversationSettings, MessagePrivacySettings
)

logger = logging.getLogger(__name__)

router = APIRouter()

async def get_message_service(db: AsyncSession = Depends(get_db)) -> MessageService:
    return MessageService(db)

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        conversation = await message_service.create_conversation(current_user.id, data)
        return conversation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/conversations", response_model=ConversationListResponse)
async def get_conversations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    return await message_service.get_conversations(current_user.id, page, size)

@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        return await message_service.get_conversation(current_user.id, conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.put("/conversations/{conversation_id}/settings")
async def update_conversation_settings(
    conversation_id: int,
    settings: ConversationSettings,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        await message_service.update_conversation_settings(
            current_user.id,
            conversation_id,
            settings.is_muted,
            settings.is_archived
        )
        return {"message": "Settings updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        message = await message_service.send_message(current_user.id, conversation_id, data)
        return message
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    before_message_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        return await message_service.get_messages(
            current_user.id, conversation_id, page, size, before_message_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.put("/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: int,
    data: MessageUpdate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        return await message_service.edit_message(current_user.id, message_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        await message_service.delete_message(current_user.id, message_id)
        return {"message": "Message deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/conversations/{conversation_id}/read")
async def mark_messages_as_read(
    conversation_id: int,
    up_to_message_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        await message_service.mark_messages_as_read(
            current_user.id, conversation_id, up_to_message_id
        )
        return {"message": "Messages marked as read"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    return await message_service.get_unread_count(current_user.id)

@router.get("/check-can-message/{user_id}")
async def check_can_message_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(get_message_service)
):
    from sqlalchemy import select

    result = await message_service.db.execute(
        select(User).where(User.id == user_id)
    )
    target_user = result.scalar_one_or_none()

    if not target_user:
        return {
            "can_message": False,
            "reason": "User not found",
            "target_user_settings": {
                "messages_enabled": False,
                "messages_from_strangers": False,
                "display_name": "Unknown"
            }
        }

    can_message, reason = await message_service.can_user_message(current_user.id, user_id)

    return {
        "can_message": can_message,
        "reason": reason,
        "target_user_settings": {
            "messages_enabled": target_user.messages_enabled,
            "messages_from_strangers": target_user.messages_from_strangers,
            "display_name": target_user.display_name
        }
    }

@router.get("/privacy-settings")
async def get_message_privacy_settings(
    current_user: User = Depends(get_current_user)
):
    return {
        "messages_enabled": current_user.messages_enabled,
        "messages_from_strangers": current_user.messages_from_strangers,
        "messages_notifications": current_user.messages_notifications
    }

@router.put("/privacy-settings")
async def update_message_privacy_settings(
    settings: MessagePrivacySettings,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    old_settings = {
        'messages_enabled': current_user.messages_enabled,
        'messages_from_strangers': current_user.messages_from_strangers,
        'messages_notifications': current_user.messages_notifications
    }

    if settings.messages_enabled is not None:
        current_user.messages_enabled = settings.messages_enabled
    if settings.messages_from_strangers is not None:
        current_user.messages_from_strangers = settings.messages_from_strangers
    if settings.messages_notifications is not None:
        current_user.messages_notifications = settings.messages_notifications

    await db.commit()

    critical_changes = (
        old_settings['messages_enabled'] != current_user.messages_enabled or
        old_settings['messages_from_strangers'] != current_user.messages_from_strangers
    )

    if critical_changes:
        await websocket_manager.broadcast_privacy_change(
            current_user.id,
            current_user.messages_enabled
        )

    return {"message": "Privacy settings updated successfully"}

@router.get("/moderation/flagged", dependencies=[Depends(get_current_admin_user)])
async def get_flagged_messages(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    message_service: MessageService = Depends(get_message_service)
):
    return await message_service.get_flagged_messages(page, size)

@router.post("/moderation/messages/{message_id}", dependencies=[Depends(get_current_admin_user)])
async def moderate_message(
    message_id: int,
    action: MessageModerationAction,
    current_admin: User = Depends(get_current_admin_user),
    message_service: MessageService = Depends(get_message_service)
):
    try:
        await message_service.moderate_message(
            current_admin.id, message_id, action.action, action.reason
        )
        return {"message": f"Message {action.action}d successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.websocket("/ws/conversations/{conversation_id}")
async def websocket_conversation(
    websocket: WebSocket,
    conversation_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    from ..core.auth import verify_token
    payload = verify_token(token, token_type="access")
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001)
        return

    message_service = MessageService(db)
    participant = await message_service._get_participant(conversation_id, int(user_id))
    if not participant:
        await websocket.close(code=4003)
        return

    await websocket_manager.connect(websocket, "conversation", conversation_id)

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data.get("type") == "typing":
                await websocket_manager.broadcast_typing_status(
                    conversation_id, int(user_id), message_data.get("is_typing", False)
                )
            elif message_data.get("type") == "mark_read":
                message_id = message_data.get("message_id")
                await message_service.mark_messages_as_read(
                    int(user_id), conversation_id, message_id
                )

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        await websocket_manager.broadcast_typing_status(conversation_id, int(user_id), False)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        websocket_manager.disconnect(websocket)

@router.websocket("/ws/user")
async def websocket_user_notifications(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    from ..core.auth import verify_token
    payload = verify_token(token, token_type="access")
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001)
        return

    await websocket_manager.connect(websocket, "user", item_id=None, user_id=int(user_id))

    try:
        message_service = MessageService(db)
        unread_count = await message_service.get_unread_count(int(user_id))
        await websocket.send_text(json.dumps({
            "type": "unread_count_update",
            "data": unread_count.model_dump()
        }))

        while True:
            data = await websocket.receive_text()

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"User WebSocket error: {e}")
        websocket_manager.disconnect(websocket)

@router.post("/admin/cleanup-old-messages", dependencies=[Depends(get_current_admin_user)])
async def cleanup_old_messages(
    days_old: int = Query(365, ge=30),
    message_service: MessageService = Depends(get_message_service)
):
    count = await message_service.cleanup_old_messages(days_old)
    return {"message": f"Cleaned up {count} old messages"}

@router.post("/admin/cleanup-empty-conversations", dependencies=[Depends(get_current_admin_user)])
async def cleanup_empty_conversations(
    message_service: MessageService = Depends(get_message_service)
):
    count = await message_service.cleanup_empty_conversations()
    return {"message": f"Cleaned up {count} empty conversations"}

@router.get("/admin/stats", dependencies=[Depends(get_current_admin_user)])
async def get_message_stats(
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import func, select
    from ..models.message import Message, Conversation

    total_messages = await db.execute(select(func.count(Message.id)))
    total_conversations = await db.execute(select(func.count(Conversation.id)))
    active_conversations = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.is_active == True)
    )
    flagged_messages = await db.execute(
        select(func.count(Message.id)).where(Message.is_flagged == True)
    )

    ws_stats = websocket_manager.get_connection_stats()

    return {
        "message_stats": {
            "total_messages": total_messages.scalar(),
            "total_conversations": total_conversations.scalar(),
            "active_conversations": active_conversations.scalar(),
            "flagged_messages": flagged_messages.scalar()
        },
        "websocket_stats": ws_stats
    }
