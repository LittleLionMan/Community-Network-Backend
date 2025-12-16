from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.email_templates import generate_new_message_notification_email
from app.services.email_service import EmailService

from ..models.message import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReadReceipt,
)
from ..models.user import User
from ..schemas.message import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationParticipantResponse,
    ConversationResponse,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    MessageUpdate,
    UnreadCountResponse,
)
from ..schemas.user import UserSummary
from .moderation_service import ModerationService
from .websocket_service import websocket_manager


class MessageService:
    db: AsyncSession
    moderation_service: ModerationService

    def __init__(self, db: AsyncSession):
        self.db = db
        self.moderation_service = ModerationService(db)

    async def can_user_message(
        self, sender_id: int, recipient_id: int
    ) -> tuple[bool, str | None]:
        if sender_id == recipient_id:
            return False, "Cannot message yourself"

        result = await self.db.execute(select(User).where(User.id == recipient_id))
        recipient = result.scalar_one_or_none()

        if not recipient or not recipient.is_active:
            return False, "User not found or inactive"

        if not recipient.messages_enabled:
            return False, "User has disabled direct messages"

        if not recipient.messages_from_strangers:
            existing_conversation = await self._get_conversation_between_users(
                sender_id, recipient_id
            )
            if not existing_conversation:
                return False, "User only accepts messages from known contacts"

        return True, None

    async def create_conversation(
        self, creator_id: int, data: ConversationCreate
    ) -> ConversationResponse:
        can_message, error = await self.can_user_message(
            creator_id, data.participant_id
        )
        if not can_message:
            raise ValueError(error)

        existing = await self._get_conversation_between_users(
            creator_id, data.participant_id
        )
        if existing:
            _ = await self.send_message(
                creator_id, existing.id, MessageCreate(content=data.initial_message)
            )
            conversations = await self.get_conversations(creator_id, 1, 1)
            for conv in conversations.conversations:
                if conv.id == existing.id:
                    return conv
            raise ValueError("Failed to retrieve conversation")

        conversation = Conversation()
        self.db.add(conversation)
        await self.db.flush()

        creator_participant = ConversationParticipant(
            conversation_id=conversation.id, user_id=creator_id
        )
        recipient_participant = ConversationParticipant(
            conversation_id=conversation.id, user_id=data.participant_id
        )

        self.db.add(creator_participant)
        self.db.add(recipient_participant)
        await self.db.flush()

        _ = await self.send_message(
            creator_id, conversation.id, MessageCreate(content=data.initial_message)
        )
        await self.db.commit()

        conversations = await self.get_conversations(creator_id, 1, 1)
        for conv in conversations.conversations:
            if conv.id == conversation.id:
                return conv

        raise ValueError("Failed to create conversation")

    async def send_message(
        self, sender_id: int, conversation_id: int, data: MessageCreate
    ) -> MessageResponse:
        participant = await self.get_participant(conversation_id, sender_id)
        if not participant:
            raise ValueError("User is not a participant in this conversation")

        moderation_result = self.moderation_service.check_content(data.content)

        now = datetime.now(timezone.utc)

        message = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=data.content,
            reply_to_id=data.reply_to_id,
            is_flagged=moderation_result.get("is_flagged", False),
            moderation_status="pending"
            if moderation_result.get("requires_review", False)
            else "approved",
            last_activity_at=now,
        )

        self.db.add(message)
        await self.db.flush()

        message_with_relations = await self.db.execute(
            select(Message)
            .options(
                selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.sender),
            )
            .where(Message.id == message.id)
        )
        message = message_with_relations.scalar_one()

        conversation = await self.db.get(Conversation, conversation_id)
        if conversation:
            conversation.last_message_at = message.created_at
            conversation.last_message_preview = data.content[:100]
            conversation.updated_at = message.created_at

        read_receipt = MessageReadReceipt(message_id=message.id, user_id=sender_id)
        self.db.add(read_receipt)

        await self.db.commit()

        await self._send_email_notifications(conversation_id, sender_id, message)

        message_response = await self._format_message(message, sender_id)
        await self._notify_conversation_participants(
            conversation_id,
            sender_id,
            {
                "type": "new_message",
                "conversation_id": conversation_id,
                "message": message_response.model_dump(mode="json"),
            },
        )

        try:
            participants_query = select(ConversationParticipant.user_id).where(
                and_(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id != sender_id,
                )
            )
            result = await self.db.execute(participants_query)
            other_participants = result.scalars().all()

            for participant_id in other_participants:
                unread = await self.get_unread_count(participant_id)
                await websocket_manager.send_to_user(
                    participant_id,
                    {"type": "unread_count_update", "data": unread.model_dump()},
                )
        except Exception as e:
            print(f"Failed to send unread updates: {e}")

        return message_response

    async def _send_email_notifications(
        self, conversation_id: int, sender_id: int, message: Message
    ):
        try:
            sender_result = await self.db.execute(
                select(User).where(User.id == sender_id)
            )
            sender = sender_result.scalar_one_or_none()
            if not sender:
                return

            participants_query = (
                select(ConversationParticipant)
                .options(selectinload(ConversationParticipant.user))
                .where(
                    and_(
                        ConversationParticipant.conversation_id == conversation_id,
                        ConversationParticipant.user_id != sender_id,
                    )
                )
            )

            result = await self.db.execute(participants_query)
            participants = result.scalars().all()

            for participant in participants:
                recipient = participant.user

                if not recipient.email_notifications_messages:
                    continue

                if websocket_manager.is_user_connected(recipient.id):
                    continue

                existing_unread_query = select(func.count(Message.id)).where(
                    and_(
                        Message.conversation_id == conversation_id,
                        Message.sender_id == sender_id,
                        Message.is_deleted.is_(False),
                        Message.id != message.id,
                        Message.id.not_in(
                            select(MessageReadReceipt.message_id).where(
                                MessageReadReceipt.user_id == recipient.id
                            )
                        ),
                    )
                )

                unread_result = await self.db.execute(existing_unread_query)
                existing_unread_count = unread_result.scalar() or 0

                if existing_unread_count == 0:
                    await self._send_new_message_email(
                        recipient=recipient,
                        sender=sender,
                        message_content=message.content,
                    )

        except Exception as e:
            print(e)

    async def _send_new_message_email(
        self, recipient: User, sender: User, message_content: str
    ):
        try:
            recipient_name = recipient.first_name or recipient.display_name
            sender_name = sender.first_name or sender.display_name

            email_html = generate_new_message_notification_email(
                recipient_name=recipient_name,
                sender_name=sender_name,
                message_preview=message_content,
            )

            EmailService.send_email(
                to_email=recipient.email,
                subject=f"Neue Nachricht von {sender_name}",
                html_content=email_html,
            )

        except Exception as e:
            print(e)

    async def get_conversations(
        self, user_id: int, page: int = 1, size: int = 20
    ) -> ConversationListResponse:
        offset = (page - 1) * size

        query = (
            select(Conversation)
            .join(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.is_archived.is_(False),
                    Conversation.is_active,
                )
            )
            .options(
                selectinload(Conversation.participants).selectinload(
                    ConversationParticipant.user
                ),
                selectinload(Conversation.messages).selectinload(Message.sender),
            )
            .order_by(desc(Conversation.last_message_at))
            .offset(offset)
            .limit(size)
        )

        result = await self.db.execute(query)
        conversations = result.scalars().all()

        count_query = (
            select(func.count(Conversation.id))
            .join(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.is_archived.is_(False),
                    Conversation.is_active,
                )
            )
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        formatted_conversations: list[ConversationResponse] = []
        for conv in conversations:
            formatted_conv = await self._format_conversation(conv, user_id)
            formatted_conversations.append(formatted_conv)

        return ConversationListResponse(
            conversations=formatted_conversations,
            total=total,
            page=page,
            size=size,
            has_more=total > page * size,
        )

    async def get_conversation(
        self, user_id: int, conversation_id: int
    ) -> ConversationDetailResponse:
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            raise ValueError("User is not a participant in this conversation")

        query = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(
                selectinload(Conversation.participants).selectinload(
                    ConversationParticipant.user
                ),
                selectinload(Conversation.messages).selectinload(Message.sender),
                selectinload(Conversation.messages).selectinload(Message.read_receipts),
            )
        )

        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError("Conversation not found")

        return await self._format_conversation_detail(conversation, user_id)

    async def get_messages(
        self,
        user_id: int,
        conversation_id: int,
        page: int = 1,
        size: int = 50,
        before_message_id: int | None = None,
    ) -> MessageListResponse:
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            raise ValueError("User is not a participant in this conversation")

        query = (
            select(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.is_deleted.is_(False),
                )
            )
            .options(
                selectinload(Message.sender),
                selectinload(Message.reply_to).selectinload(Message.sender),
                selectinload(Message.read_receipts),
            )
        )

        if before_message_id:
            query = query.where(Message.id < before_message_id)

        query = query.order_by(desc(Message.last_activity_at)).limit(size)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        count_query = select(func.count(Message.id)).where(
            and_(
                Message.conversation_id == conversation_id,
                Message.is_deleted.is_(False),
            )
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        formatted_messages: list[MessageResponse] = []
        for message in reversed(messages):
            formatted_msg = await self._format_message(message, user_id)
            formatted_messages.append(formatted_msg)

        return MessageListResponse(
            messages=formatted_messages,
            total=total,
            page=page,
            size=size,
            has_more=len(messages) == size,
        )

    async def mark_messages_as_read(
        self, user_id: int, conversation_id: int, up_to_message_id: int | None = None
    ):
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            raise ValueError("User is not a participant in this conversation")

        query = select(Message.id).where(
            and_(
                Message.conversation_id == conversation_id,
                Message.is_deleted.is_(False),
                or_(
                    Message.message_type == "transaction",
                    Message.sender_id != user_id,
                ),
            )
        )

        if up_to_message_id:
            query = query.where(Message.id <= up_to_message_id)

        read_subquery = select(MessageReadReceipt.message_id).where(
            MessageReadReceipt.user_id == user_id
        )
        query = query.where(Message.id.not_in(read_subquery))

        result = await self.db.execute(query)
        unread_message_ids = result.scalars().all()

        read_receipts = [
            MessageReadReceipt(message_id=msg_id, user_id=user_id)
            for msg_id in unread_message_ids
        ]

        self.db.add_all(read_receipts)
        participant.last_read_at = datetime.now(timezone.utc)

        await self.db.commit()

        await self._notify_conversation_participants(
            conversation_id,
            user_id,
            {
                "type": "messages_read",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "read_up_to": up_to_message_id,
            },
        )

    async def get_unread_count(self, user_id: int) -> UnreadCountResponse:
        conversations_query = select(ConversationParticipant.conversation_id).where(
            and_(
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.is_archived.is_(False),
            )
        )

        result = await self.db.execute(conversations_query)
        conversation_ids = result.scalars().all()

        conversation_counts: list[dict[str, object]] = []
        total_unread = 0

        for conv_id in conversation_ids:
            unread_query = select(func.count(Message.id)).where(
                and_(
                    Message.conversation_id == conv_id,
                    Message.is_deleted.is_(False),
                    Message.id.not_in(
                        select(MessageReadReceipt.message_id).where(
                            MessageReadReceipt.user_id == user_id
                        )
                    ),
                    or_(
                        Message.message_type == "transaction",
                        Message.sender_id != user_id,
                    ),
                )
            )

            unread_result = await self.db.execute(unread_query)
            unread_count = unread_result.scalar() or 0

            if unread_count > 0:
                conversation_counts.append(
                    {"conversation_id": conv_id, "unread_count": unread_count}
                )
                total_unread += unread_count

        return UnreadCountResponse(
            total_unread=total_unread, conversations=conversation_counts
        )

    async def edit_message(
        self, user_id: int, message_id: int, data: MessageUpdate
    ) -> MessageResponse:
        result = await self.db.execute(
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.sender))
        )
        message = result.scalar_one_or_none()

        if not message:
            raise ValueError("Message not found")

        if message.sender_id != user_id:
            raise ValueError("Can only edit your own messages")

        if message.is_deleted:
            raise ValueError("Cannot edit deleted message")

        edit_deadline = message.created_at + timedelta(minutes=15)
        if datetime.now(timezone.utc) > edit_deadline:
            raise ValueError("Edit time limit exceeded")

        moderation_result = self.moderation_service.check_content(data.content)

        message.content = data.content
        message.edited_at = datetime.now(timezone.utc)
        message.is_edited = True
        message.is_flagged = moderation_result.get("is_flagged", False)
        message.moderation_status = (
            "pending" if moderation_result.get("requires_review", False) else "approved"
        )

        await self.db.commit()

        message_response = await self._format_message(message, user_id)
        await self._notify_conversation_participants(
            message.conversation_id,
            user_id,
            {
                "type": "message_edited",
                "conversation_id": message.conversation_id,
                "message": message_response.model_dump(),
            },
        )

        return message_response

    async def delete_message(self, user_id: int, message_id: int) -> bool:
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()

        if not message:
            raise ValueError("Message not found")

        if message.sender_id != user_id:
            raise ValueError("Can only delete your own messages")

        message.is_deleted = True
        message.content = "[Message deleted]"

        await self.db.commit()

        await self._notify_conversation_participants(
            message.conversation_id,
            user_id,
            {
                "type": "message_deleted",
                "conversation_id": message.conversation_id,
                "message_id": message_id,
            },
        )

        return True

    async def update_conversation_settings(
        self,
        user_id: int,
        conversation_id: int,
        is_muted: bool | None = None,
        is_archived: bool | None = None,
    ) -> bool:
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            raise ValueError("User is not a participant in this conversation")

        if is_muted is not None:
            participant.is_muted = is_muted

        if is_archived is not None:
            participant.is_archived = is_archived

        await self.db.commit()
        return True

    async def _get_conversation_between_users(
        self, user1_id: int, user2_id: int
    ) -> Conversation | None:
        subquery = (
            select(ConversationParticipant.conversation_id)
            .where(ConversationParticipant.user_id == user1_id)
            .intersect(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.user_id == user2_id
                )
            )
        )

        final_query = select(Conversation).where(Conversation.id.in_(subquery)).limit(1)

        result = await self.db.execute(final_query)
        return result.scalar_one_or_none()

    async def get_participant(
        self, conversation_id: int, user_id: int
    ) -> ConversationParticipant | None:
        result = await self.db.execute(
            select(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _format_message(
        self, message: Message, current_user_id: int
    ) -> MessageResponse:
        is_read = False
        if message.message_type == "transaction":
            read_receipt_query = select(MessageReadReceipt).where(
                and_(
                    MessageReadReceipt.message_id == message.id,
                    MessageReadReceipt.user_id == current_user_id,
                )
            )
            read_result = await self.db.execute(read_receipt_query)
            is_read = read_result.scalar_one_or_none() is not None
        elif message.sender_id == current_user_id:
            is_read = True
        else:
            read_receipt_query = select(MessageReadReceipt).where(
                and_(
                    MessageReadReceipt.message_id == message.id,
                    MessageReadReceipt.user_id == current_user_id,
                )
            )
            read_result = await self.db.execute(read_receipt_query)
            is_read = read_result.scalar_one_or_none() is not None

        reply_to = None
        if message.reply_to:
            reply_to = MessageResponse(
                id=message.reply_to.id,
                conversation_id=message.reply_to.conversation_id,
                sender=UserSummary.model_validate(
                    message.reply_to.sender, from_attributes=True
                ),
                content=message.reply_to.content[:100] + "..."
                if len(message.reply_to.content) > 100
                else message.reply_to.content,
                message_type=message.reply_to.message_type,
                created_at=message.reply_to.created_at,
                edited_at=message.reply_to.edited_at,
                is_edited=message.reply_to.is_edited,
                is_deleted=message.reply_to.is_deleted,
                reply_to_id=None,
                is_read=True,
            )

        transaction_data = message.transaction_data
        if message.message_type == "transaction" and transaction_data:
            transaction_data = await self._recompute_transaction_permissions(
                transaction_data, current_user_id
            )

        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender=UserSummary.model_validate(message.sender, from_attributes=True),
            content=message.content,
            message_type=message.message_type,
            created_at=message.created_at,
            edited_at=message.edited_at,
            is_edited=message.is_edited,
            is_deleted=message.is_deleted,
            reply_to_id=message.reply_to_id,
            reply_to=reply_to,
            is_read=is_read,
            transaction_data=transaction_data,
        )

    async def _format_conversation(
        self, conversation: Conversation, current_user_id: int
    ) -> ConversationResponse:
        participants: list[ConversationParticipantResponse] = []
        for participant in conversation.participants:
            if participant.user_id != current_user_id:
                participants.append(
                    ConversationParticipantResponse(
                        user=UserSummary.model_validate(
                            participant.user, from_attributes=True
                        ),
                        joined_at=participant.joined_at,
                        last_read_at=participant.last_read_at,
                        is_muted=participant.is_muted,
                        is_archived=participant.is_archived,
                    )
                )

        last_message = None
        if hasattr(conversation, "messages") and conversation.messages:
            latest_msg = max(conversation.messages, key=lambda m: m.last_activity_at)
            last_message = await self._format_message(latest_msg, current_user_id)

        unread_count = await self._get_unread_count_for_conversation(
            conversation.id, current_user_id
        )

        return ConversationResponse(
            id=conversation.id,
            participants=participants,
            last_message=last_message,
            last_message_at=conversation.last_message_at,
            unread_count=unread_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    async def _format_conversation_detail(
        self, conversation: Conversation, current_user_id: int
    ) -> ConversationDetailResponse:
        participants: list[ConversationParticipantResponse] = []
        for participant in conversation.participants:
            participants.append(
                ConversationParticipantResponse(
                    user=UserSummary.model_validate(
                        participant.user, from_attributes=True
                    ),
                    joined_at=participant.joined_at,
                    last_read_at=participant.last_read_at,
                    is_muted=participant.is_muted,
                    is_archived=participant.is_archived,
                )
            )

        recent_messages = sorted(
            [msg for msg in conversation.messages if not msg.is_deleted],
            key=lambda m: m.last_activity_at,
            reverse=True,
        )[:50]

        messages: list[MessageResponse] = []
        for message in reversed(recent_messages):
            formatted_msg = await self._format_message(message, current_user_id)
            messages.append(formatted_msg)

        unread_count = await self._get_unread_count_for_conversation(
            conversation.id, current_user_id
        )

        return ConversationDetailResponse(
            id=conversation.id,
            participants=participants,
            messages=messages,
            unread_count=unread_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            has_more=len(conversation.messages) > 50,
        )

    async def _get_unread_count_for_conversation(
        self, conversation_id: int, user_id: int
    ) -> int:
        unread_query = select(func.count(Message.id)).where(
            and_(
                Message.conversation_id == conversation_id,
                Message.sender_id != user_id,
                Message.is_deleted.is_(False),
                Message.id.not_in(
                    select(MessageReadReceipt.message_id).where(
                        MessageReadReceipt.user_id == user_id
                    )
                ),
            )
        )

        result = await self.db.execute(unread_query)
        return result.scalar() or 0

    async def _notify_conversation_participants(
        self, conversation_id: int, exclude_user_id: int | None, data: dict[str, object]
    ):
        try:
            participants_query = select(ConversationParticipant.user_id).where(
                ConversationParticipant.conversation_id == conversation_id
            )

            if exclude_user_id:
                participants_query = participants_query.where(
                    ConversationParticipant.user_id != exclude_user_id
                )

            result = await self.db.execute(participants_query)
            participant_ids = result.scalars().all()

            for user_id in participant_ids:
                await websocket_manager.send_to_user(user_id, data)

        except Exception as e:
            print(f"Failed to send WebSocket notification: {e}")

    async def cleanup_old_messages(self, days_old: int = 365):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        result = await self.db.execute(
            select(func.count(Message.id)).where(
                and_(Message.is_deleted, Message.created_at < cutoff_date)
            )
        )
        count = result.scalar() or 0

        if count > 0:
            _ = await self.db.execute(
                delete(Message).where(
                    and_(Message.is_deleted, Message.created_at < cutoff_date)
                )
            )
            await self.db.commit()

        return count

    async def cleanup_empty_conversations(self):
        conversations_with_messages = select(Message.conversation_id.distinct())

        empty_conversations_query = select(Conversation.id).where(
            and_(
                Conversation.id.not_in(conversations_with_messages),
                Conversation.created_at
                < datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )

        result = await self.db.execute(empty_conversations_query)
        empty_conversation_ids = result.scalars().all()

        if empty_conversation_ids:
            _ = await self.db.execute(
                delete(ConversationParticipant).where(
                    ConversationParticipant.conversation_id.in_(empty_conversation_ids)
                )
            )

            _ = await self.db.execute(
                delete(Conversation).where(Conversation.id.in_(empty_conversation_ids))
            )

            await self.db.commit()

        return len(empty_conversation_ids)

    async def get_flagged_messages(self, page: int = 1, size: int = 20):
        offset = (page - 1) * size

        query = (
            select(Message)
            .where(or_(Message.is_flagged, Message.moderation_status == "pending"))
            .options(selectinload(Message.sender), selectinload(Message.conversation))
            .order_by(desc(Message.created_at))
            .offset(offset)
            .limit(size)
        )

        result = await self.db.execute(query)
        messages = result.scalars().all()

        count_query = select(func.count(Message.id)).where(
            or_(Message.is_flagged, Message.moderation_status == "pending")
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        return {
            "messages": messages,
            "total": total,
            "page": page,
            "size": size,
            "has_more": total > page * size,
        }

    async def moderate_message(
        self, admin_id: int, message_id: int, action: str, reason: str | None = None
    ):
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()

        if not message:
            raise ValueError("Message not found")

        if action == "approve":
            message.moderation_status = "approved"
            message.is_flagged = False
        elif action == "reject":
            message.moderation_status = "rejected"
            message.is_deleted = True
            message.content = "[Message removed by moderator]"
        elif action == "flag":
            message.is_flagged = True
            message.moderation_status = "pending"

        message.moderation_reason = reason
        message.moderated_at = datetime.now(timezone.utc)
        message.moderated_by = admin_id

        await self.db.commit()

        if action == "reject":
            await self._notify_conversation_participants(
                message.conversation_id,
                None,
                {
                    "type": "message_moderated",
                    "conversation_id": message.conversation_id,
                    "message_id": message_id,
                    "action": "removed",
                },
            )

        return True

    async def _recompute_transaction_permissions(
        self, transaction_data: dict[str, str | int | bool | None], current_user_id: int
    ) -> dict[str, str | int | bool | None]:
        transaction_id = transaction_data.get("transaction_id")
        if not transaction_id or not isinstance(transaction_id, int):
            return transaction_data

        from app.models.exchange_transaction import ExchangeTransaction
        from app.models.exchange_transaction import (
            TransactionStatus as ModelTransactionStatus,
        )

        result = await self.db.execute(
            select(ExchangeTransaction).where(ExchangeTransaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()

        if not transaction:
            return transaction_data

        proposed_by = transaction.transaction_metadata.get("proposed_by_user_id")
        is_provider = current_user_id == transaction.provider_id
        can_update = transaction.can_be_updated()

        can_propose_time = (
            can_update and transaction.status == ModelTransactionStatus.PENDING
        )

        can_confirm_time = (
            can_update
            and transaction.status == ModelTransactionStatus.PENDING
            and len(transaction.proposed_times) > 0
            and proposed_by is not None
            and proposed_by != current_user_id
        )

        can_edit_address = (
            is_provider
            and transaction.status == ModelTransactionStatus.PENDING
            and can_update
        )

        updated_data: dict[str, str | int | bool | None] = dict(transaction_data)
        updated_data.update(
            {
                "can_propose_time": can_propose_time,
                "can_confirm_time": can_confirm_time,
                "can_edit_address": can_edit_address,
                "can_confirm_handover": can_update
                and transaction.status == ModelTransactionStatus.TIME_CONFIRMED,
                "can_cancel": can_update
                and transaction.status
                in (
                    ModelTransactionStatus.PENDING,
                    ModelTransactionStatus.TIME_CONFIRMED,
                ),
            }
        )

        return updated_data
