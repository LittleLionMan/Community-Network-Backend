import logging
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.book_offer import BookOffer
from app.models.exchange_transaction import (
    ExchangeTransaction,
)
from app.models.exchange_transaction import (
    TransactionStatus as ModelTransactionStatus,
)
from app.models.exchange_transaction import (
    TransactionType as ModelTransactionType,
)
from app.models.message import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReadReceipt,
)
from app.models.user import User
from app.schemas.transaction import (
    ConfirmTimeRequest,
    ProposeTimeRequest,
    TransactionCreate,
    TransactionData,
    TransactionHistoryItem,
    TransactionOfferInfo,
    TransactionParticipantInfo,
)
from app.services.availability_service import AvailabilityService
from app.services.message_service import MessageService
from app.services.websocket_service import websocket_manager
from app.utils.datetime_utils import serialize_datetime, serialize_datetime_list

logger = logging.getLogger(__name__)


class OfferInfo(TypedDict):
    owner_id: int
    is_available: bool
    title: str
    thumbnail_url: str | None
    condition: str | None
    location_address: str


class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count_active_transactions(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ExchangeTransaction.id)).where(
                ExchangeTransaction.requester_id == user_id,
                ExchangeTransaction.status.in_(
                    [
                        ModelTransactionStatus.PENDING,
                        ModelTransactionStatus.TIME_CONFIRMED,
                    ]
                ),
            )
        )
        return result.scalar_one()

    def _serialize_transaction_for_message(
        self,
        transaction: ExchangeTransaction,
        requester_name: str,
        provider_name: str,
        requester_avatar: str | None,
        provider_avatar: str | None,
        offer_title: str,
        offer_thumbnail: str | None,
        offer_condition: str | None,
        current_user_id: int,
    ) -> dict[str, str | int | bool | None]:
        proposed_times_str = ",".join(
            serialize_datetime_list(transaction.proposed_times)
        )

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

        return {
            "transaction_id": transaction.id,
            "transaction_type": transaction.transaction_type
            if isinstance(transaction.transaction_type, str)
            else transaction.transaction_type.value,
            "status": transaction.status.value
            if hasattr(transaction.status, "value")
            else transaction.status,
            "offer_id": transaction.offer_id,
            "offer_type": transaction.offer_type,
            "offer_title": offer_title,
            "offer_thumbnail_url": offer_thumbnail,
            "offer_condition": offer_condition,
            "requester_id": transaction.requester_id,
            "requester_display_name": requester_name,
            "requester_profile_image_url": requester_avatar,
            "provider_id": transaction.provider_id,
            "provider_display_name": provider_name,
            "provider_profile_image_url": provider_avatar,
            "proposed_times": proposed_times_str,
            "confirmed_time": serialize_datetime(transaction.confirmed_time),
            "exact_address": transaction.exact_address,
            "requester_confirmed": transaction.requester_confirmed_handover,
            "provider_confirmed": transaction.provider_confirmed_handover,
            "created_at": serialize_datetime(transaction.created_at),
            "updated_at": serialize_datetime(
                transaction.time_confirmed_at or transaction.created_at
            ),
            "expires_at": serialize_datetime(transaction.expires_at),
            "is_expired": transaction.is_expired(),
            "can_propose_time": can_propose_time,
            "can_confirm_time": can_confirm_time,
            "can_edit_address": can_edit_address,
            "can_confirm_handover": can_update
            and transaction.status == ModelTransactionStatus.TIME_CONFIRMED,
            "can_cancel": can_update
            and transaction.status
            in (ModelTransactionStatus.PENDING, ModelTransactionStatus.TIME_CONFIRMED),
        }

    async def _update_message_transaction_data(
        self,
        transaction: ExchangeTransaction,
        user_id: int,
    ) -> None:
        message = await self._get_message(transaction.message_id)

        result = await self.db.execute(
            select(User).where(
                User.id.in_([transaction.requester_id, transaction.provider_id])
            )
        )
        users = {u.id: u for u in result.scalars().all()}

        offer_info = await self._get_offer_info(
            transaction.offer_type, transaction.offer_id
        )

        requester_data = self._serialize_transaction_for_message(
            transaction=transaction,
            requester_name=users[transaction.requester_id].display_name,
            provider_name=users[transaction.provider_id].display_name,
            requester_avatar=users[transaction.requester_id].profile_image_url,
            provider_avatar=users[transaction.provider_id].profile_image_url,
            offer_title=offer_info["title"],
            offer_thumbnail=offer_info["thumbnail_url"],
            offer_condition=offer_info["condition"],
            current_user_id=transaction.requester_id,
        )

        provider_data = self._serialize_transaction_for_message(
            transaction=transaction,
            requester_name=users[transaction.requester_id].display_name,
            provider_name=users[transaction.provider_id].display_name,
            requester_avatar=users[transaction.requester_id].profile_image_url,
            provider_avatar=users[transaction.provider_id].profile_image_url,
            offer_title=offer_info["title"],
            offer_thumbnail=offer_info["thumbnail_url"],
            offer_condition=offer_info["condition"],
            current_user_id=transaction.provider_id,
        )

        message.transaction_data = requester_data

        now = datetime.now(timezone.utc)
        message.last_activity_at = now

        conversation = await self.db.get(Conversation, message.conversation_id)
        conversation_preview = self._get_transaction_preview(transaction)

        if conversation:
            conversation.last_message_at = now
            conversation.updated_at = now
            conversation.last_message_preview = conversation_preview

        participants_query = select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == message.conversation_id,
        )
        participants_result = await self.db.execute(participants_query)
        all_participants = participants_result.scalars().all()

        await websocket_manager.send_to_user(
            transaction.requester_id,
            {
                "type": "transaction_updated",
                "conversation_id": message.conversation_id,
                "message_id": message.id,
                "transaction_id": transaction.id,
                "transaction_data": requester_data,
            },
        )

        await websocket_manager.send_to_user(
            transaction.provider_id,
            {
                "type": "transaction_updated",
                "conversation_id": message.conversation_id,
                "message_id": message.id,
                "transaction_id": transaction.id,
                "transaction_data": provider_data,
            },
        )

        for participant in all_participants:
            if participant.user_id == user_id:
                continue

            delete_receipt = delete(MessageReadReceipt).where(
                and_(
                    MessageReadReceipt.message_id == message.id,
                    MessageReadReceipt.user_id == participant.user_id,
                )
            )
            _ = await self.db.execute(delete_receipt)

        await self.db.flush()

        msg_service = MessageService(self.db)

        for participant in all_participants:
            user_unread = await msg_service.get_unread_count(participant.user_id)

            conv_unread = 0
            for conv in user_unread.conversations:
                if conv["conversation_id"] == message.conversation_id:
                    conv_unread = conv["unread_count"]
                    break

            await websocket_manager.send_to_user(
                participant.user_id,
                {
                    "type": "conversation_updated",
                    "conversation_id": message.conversation_id,
                    "unread_count": conv_unread,
                    "last_message_preview": conversation.last_message_preview
                    if conversation
                    else None,
                    "last_message_at": now.isoformat(),
                },
            )

            await websocket_manager.send_to_user(
                participant.user_id,
                {
                    "type": "unread_count_update",
                    "data": user_unread.model_dump(),
                },
            )

            user_unread = await msg_service.get_unread_count(participant.user_id)
            await websocket_manager.send_to_user(
                participant.user_id,
                {
                    "type": "unread_count_update",
                    "data": user_unread.model_dump(),
                },
            )

    async def create_transaction(
        self,
        requester_id: int,
        provider_id: int,
        conversation_id: int,
        data: TransactionCreate,
    ) -> TransactionData:
        if requester_id == provider_id:
            raise HTTPException(
                status_code=400, detail="Cannot create transaction with yourself"
            )

        result = await self.db.execute(select(User).where(User.id == requester_id))
        requester = result.scalar_one_or_none()
        if not requester:
            raise HTTPException(status_code=404, detail="Requester not found")

        if requester.book_credits_remaining < 1:
            raise HTTPException(
                status_code=400,
                detail="Insufficient credits. You need at least 1 credit to request a book.",
            )

        active_count = await self._count_active_transactions(requester_id)
        if active_count >= requester.book_credits_remaining:
            raise HTTPException(
                status_code=400,
                detail=f"Too many active transactions. You can only have {requester.book_credits_remaining} active transaction(s) at a time. Cancel an existing transaction to start a new one.",
            )

        offer_info = await self._get_offer_info(data.offer_type, data.offer_id)

        if offer_info["owner_id"] != provider_id:
            raise HTTPException(
                status_code=403, detail="Provider does not own this offer"
            )

        if not offer_info["is_available"]:
            raise HTTPException(status_code=400, detail="Offer is no longer available")

        existing = await self._get_active_transaction(
            data.offer_type, data.offer_id, requester_id
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Active transaction already exists for this offer",
            )

        if conversation_id == 0:
            conversation_id = await self._get_or_create_conversation(
                requester_id, provider_id
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)

        proposed_times_iso = [
            t.isoformat() if isinstance(t, datetime) else t for t in data.proposed_times
        ]

        transaction_message = Message(
            conversation_id=conversation_id,
            sender_id=requester_id,
            message_type="transaction",
            content=data.initial_message,
            transaction_data={},
            created_at=now,
            last_activity_at=now,
        )
        self.db.add(transaction_message)
        await self.db.flush()

        meeting_location = await self._get_meeting_location_from_offer(
            data.offer_type, data.offer_id
        )

        transaction_metadata = self._build_metadata(
            data, offer_info, requester_id if proposed_times_iso else None
        )

        transaction = ExchangeTransaction(
            message_id=transaction_message.id,
            transaction_type=data.transaction_type.value,
            offer_type=data.offer_type,
            offer_id=data.offer_id,
            requester_id=requester_id,
            provider_id=provider_id,
            status=ModelTransactionStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            proposed_times=proposed_times_iso,
            exact_address=meeting_location,
            transaction_metadata=transaction_metadata,
        )

        self.db.add(transaction)
        await self.db.flush()

        if data.offer_type == "book_offer":
            await self._reserve_book_offer(data.offer_id, requester_id, expires_at)

        result = await self.db.execute(
            select(User).where(User.id.in_([requester_id, provider_id]))
        )
        users = {u.id: u for u in result.scalars().all()}

        transaction_message.transaction_data = self._serialize_transaction_for_message(
            transaction=transaction,
            requester_name=users[requester_id].display_name,
            provider_name=users[provider_id].display_name,
            requester_avatar=users[requester_id].profile_image_url,
            provider_avatar=users[provider_id].profile_image_url,
            offer_title=offer_info["title"],
            offer_thumbnail=offer_info["thumbnail_url"],
            offer_condition=offer_info["condition"],
            current_user_id=requester_id,
        )

        requester_receipt = MessageReadReceipt(
            message_id=transaction_message.id, user_id=requester_id
        )
        self.db.add(requester_receipt)

        await self.db.commit()
        await self.db.refresh(transaction_message)

        await websocket_manager.send_to_conversation(
            conversation_id,
            {
                "type": "new_message",
                "conversation_id": conversation_id,
                "message": {
                    "id": transaction_message.id,
                    "conversation_id": conversation_id,
                    "sender": {
                        "id": requester_id,
                        "display_name": users[requester_id].display_name,
                        "profile_image_url": users[requester_id].profile_image_url,
                    },
                    "content": data.initial_message,
                    "message_type": "transaction",
                    "transaction_data": transaction_message.transaction_data,
                    "created_at": serialize_datetime(transaction_message.created_at),
                    "is_read": False,
                    "is_edited": False,
                    "is_deleted": False,
                },
            },
        )

        conversation = await self.db.get(Conversation, conversation_id)
        if conversation:
            conversation.last_message_at = now
            conversation.updated_at = now
            conversation.last_message_preview = self._get_transaction_preview(
                transaction
            )
            await self.db.commit()

            provider_unread_query = select(func.count(Message.id)).where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.sender_id != provider_id,
                    Message.is_deleted.is_(False),
                    Message.id.not_in(
                        select(MessageReadReceipt.message_id).where(
                            MessageReadReceipt.user_id == provider_id
                        )
                    ),
                )
            )
            provider_unread_result = await self.db.execute(provider_unread_query)
            provider_unread_count = provider_unread_result.scalar() or 0

            await websocket_manager.send_to_user(
                provider_id,
                {
                    "type": "conversation_updated",
                    "conversation_id": conversation_id,
                    "unread_count": provider_unread_count,
                    "last_message_preview": conversation.last_message_preview,
                    "last_message_at": now.isoformat(),
                },
            )

        return await self._build_transaction_data(transaction, requester_id)

    async def propose_time(
        self,
        transaction_id: int,
        user_id: int,
        data: ProposeTimeRequest,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        if transaction.status != ModelTransactionStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Can only propose times for pending transactions",
            )

        if not transaction.can_be_updated():
            raise HTTPException(status_code=400, detail="Transaction cannot be updated")

        proposed_times_iso = [t.isoformat() for t in data.proposed_times]
        is_provider = user_id == transaction.provider_id

        if is_provider:
            for proposed_time in data.proposed_times:
                provider_available = await AvailabilityService.check_time_available(
                    db=self.db,
                    user_id=transaction.provider_id,
                    check_start=proposed_time,
                    check_end=proposed_time + timedelta(hours=1),
                )

                if not provider_available:
                    logger.warning(
                        f"Provider proposed unavailable time: {proposed_time}"
                    )

        transaction.proposed_times = proposed_times_iso

        new_metadata = dict(transaction.transaction_metadata)
        new_metadata["proposed_by_user_id"] = user_id
        transaction.transaction_metadata = new_metadata

        await self._update_message_transaction_data(transaction, user_id)

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Time proposed for transaction {transaction_id} by user {user_id}")

        return await self._build_transaction_data(transaction, user_id)

    async def confirm_time(
        self,
        transaction_id: int,
        user_id: int,
        data: ConfirmTimeRequest,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        if transaction.status != ModelTransactionStatus.PENDING:
            raise HTTPException(
                status_code=400, detail="Can only confirm time for pending transactions"
            )

        if not transaction.can_be_updated():
            raise HTTPException(status_code=400, detail="Transaction cannot be updated")

        confirmed_dt = datetime.fromisoformat(
            data.confirmed_time.replace("Z", "+00:00")
        )

        provider_available = await AvailabilityService.check_time_available(
            db=self.db,
            user_id=transaction.provider_id,
            check_start=confirmed_dt,
            check_end=confirmed_dt + timedelta(hours=1),
        )

        if not provider_available:
            raise HTTPException(
                status_code=409, detail="Provider is not available at this time"
            )

        transaction.status = ModelTransactionStatus.TIME_CONFIRMED
        transaction.confirmed_time = confirmed_dt

        if not transaction.exact_address:
            transaction.exact_address = data.exact_address

        transaction.time_confirmed_at = datetime.now(timezone.utc)
        transaction.expires_at = confirmed_dt + timedelta(days=365)

        _ = await AvailabilityService.block_time_for_transaction(
            db=self.db,
            transaction_id=transaction.id,
            user_id=transaction.provider_id,
            start_time=confirmed_dt,
            end_time=confirmed_dt + timedelta(hours=1),
            title=f"Buchübergabe: {transaction.transaction_metadata.get('offer_title', 'Unbekannt')}",
        )

        _ = await AvailabilityService.block_time_for_transaction(
            db=self.db,
            transaction_id=transaction.id,
            user_id=transaction.requester_id,
            start_time=confirmed_dt,
            end_time=confirmed_dt + timedelta(hours=1),
            title=f"Buchabholung: {transaction.transaction_metadata.get('offer_title', 'Unbekannt')}",
        )

        await self._update_message_transaction_data(transaction, user_id)

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(
            f"Time confirmed for transaction {transaction_id} by user {user_id}"
        )

        return await self._build_transaction_data(transaction, user_id)

    async def update_exact_address(
        self,
        transaction_id: int,
        user_id: int,
        new_address: str,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if transaction.provider_id != user_id:
            raise HTTPException(
                status_code=403, detail="Only provider can update meeting address"
            )

        if transaction.status != ModelTransactionStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Address can only be changed before time confirmation",
            )

        transaction.exact_address = new_address

        await self._update_message_transaction_data(transaction, user_id)

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(
            f"Address updated for transaction {transaction_id} by user {user_id}"
        )

        return await self._build_transaction_data(transaction, user_id)

    async def confirm_handover(
        self, transaction_id: int, user_id: int
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        if transaction.status != ModelTransactionStatus.TIME_CONFIRMED:
            raise HTTPException(
                status_code=400, detail="Time must be confirmed before handover"
            )

        if user_id == transaction.requester_id:
            transaction.requester_confirmed_handover = True
        else:
            transaction.provider_confirmed_handover = True

        if (
            transaction.requester_confirmed_handover
            and transaction.provider_confirmed_handover
        ):
            transaction.status = ModelTransactionStatus.COMPLETED
            transaction.completed_at = datetime.now(timezone.utc)

            await self._transfer_credits(transaction)
            await self._mark_offer_unavailable(
                transaction.offer_type, transaction.offer_id
            )

        await self._update_message_transaction_data(transaction, user_id)

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(
            f"Handover confirmed for transaction {transaction_id} by user {user_id}"
        )

        return await self._build_transaction_data(transaction, user_id)

    async def cancel_transaction(
        self,
        transaction_id: int,
        user_id: int,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        if not transaction.can_be_updated():
            raise HTTPException(
                status_code=400, detail="Transaction cannot be cancelled"
            )

        transaction.status = ModelTransactionStatus.CANCELLED

        if transaction.offer_type == "book_offer":
            await self._unreserve_book_offer(transaction.offer_id)

        await AvailabilityService.remove_transaction_blocks(
            db=self.db,
            transaction_id=transaction.id,
        )

        await self._update_message_transaction_data(transaction, user_id)

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Transaction {transaction_id} cancelled by user {user_id}")

        return await self._build_transaction_data(transaction, user_id)

    async def get_transaction(
        self, transaction_id: int, user_id: int
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        return await self._build_transaction_data(transaction, user_id)

    async def get_user_transactions(
        self,
        user_id: int,
        status_filter: ModelTransactionStatus | None = None,
        limit: int = 50,
    ) -> list[TransactionHistoryItem]:
        query = select(ExchangeTransaction).where(
            (ExchangeTransaction.requester_id == user_id)
            | (ExchangeTransaction.provider_id == user_id)
        )

        if status_filter:
            query = query.where(ExchangeTransaction.status == status_filter)

        query = query.order_by(ExchangeTransaction.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        items: list[TransactionHistoryItem] = []
        for t in transactions:
            offer_info = await self._get_offer_info(t.offer_type, t.offer_id)

            other_party_id = (
                t.provider_id if t.requester_id == user_id else t.requester_id
            )
            result_user = await self.db.execute(
                select(User).where(User.id == other_party_id)
            )
            other_user = result_user.scalar_one()

            items.append(
                TransactionHistoryItem(
                    transaction_id=t.id,
                    transaction_type=ModelTransactionType(t.transaction_type),
                    status=ModelTransactionStatus(t.status),
                    offer_title=offer_info["title"],
                    offer_thumbnail=offer_info["thumbnail_url"],
                    counterpart_name=other_user.display_name,
                    counterpart_avatar=other_user.profile_image_url,
                    confirmed_time=t.confirmed_time.isoformat()
                    if t.confirmed_time
                    else None,
                    created_at=t.created_at,
                )
            )

        return items

    async def get_user_available_request_slots(self, user_id: int) -> dict[str, int]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        active_count = await self._count_active_transactions(user_id)
        available_slots = max(0, user.book_credits_remaining - active_count)

        return {
            "total_credits": user.book_credits_remaining,
            "active_transactions": active_count,
            "available_slots": available_slots,
        }

    def _get_transaction_preview(self, transaction: ExchangeTransaction) -> str:
        status_previews = {
            "pending": "📚 Buchausleihe angefragt",
            "time_confirmed": "📅 Termin bestätigt",
            "completed": "✅ Übergabe abgeschlossen",
            "cancelled": "🚫 Storniert",
            "expired": "⏰ Abgelaufen",
        }

        status_text = status_previews.get(
            transaction.status.value
            if hasattr(transaction.status, "value")
            else transaction.status,
            "Transaction-Update",
        )

        offer_title = transaction.transaction_metadata.get("offer_title", "Unbekannt")
        return f"{status_text}: {offer_title[:50]}"

    async def _get_transaction_or_404(self, transaction_id: int) -> ExchangeTransaction:
        result = await self.db.execute(
            select(ExchangeTransaction).where(ExchangeTransaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return transaction

    async def _get_message(self, message_id: int) -> Message:
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        return message

    async def _get_offer_info(self, offer_type: str, offer_id: int) -> OfferInfo:
        if offer_type == "book_offer":
            result = await self.db.execute(
                select(BookOffer)
                .options(selectinload(BookOffer.book))
                .where(BookOffer.id == offer_id)
            )
            offer = result.scalar_one_or_none()
            if not offer:
                raise HTTPException(status_code=404, detail="Offer not found")

            return OfferInfo(
                owner_id=offer.owner_id,
                is_available=offer.is_available,
                title=offer.book.title if offer.book else "Unknown",
                thumbnail_url=offer.book.cover_image_url if offer.book else None,
                condition=offer.condition.value if offer.condition else None,
                location_address=f"{offer.location_district or 'Unknown'}, Münster",
            )

        raise HTTPException(status_code=400, detail=f"Unknown offer type: {offer_type}")

    async def _get_active_transaction(
        self,
        offer_type: str,
        offer_id: int,
        requester_id: int,
    ) -> ExchangeTransaction | None:
        result = await self.db.execute(
            select(ExchangeTransaction).where(
                ExchangeTransaction.offer_type == offer_type,
                ExchangeTransaction.offer_id == offer_id,
                ExchangeTransaction.requester_id == requester_id,
                ExchangeTransaction.status.in_(
                    [
                        ModelTransactionStatus.PENDING,
                        ModelTransactionStatus.TIME_CONFIRMED,
                    ]
                ),
            )
        )
        return result.scalar_one_or_none()

    async def _get_or_create_conversation(self, user1_id: int, user2_id: int) -> int:
        subquery = (
            select(ConversationParticipant.conversation_id)
            .where(ConversationParticipant.user_id == user1_id)
            .intersect(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.user_id == user2_id
                )
            )
        )

        result = await self.db.execute(
            select(Conversation).where(Conversation.id.in_(subquery)).limit(1)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return existing.id

        now = datetime.now(timezone.utc)
        new_conversation = Conversation(
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        self.db.add(new_conversation)
        await self.db.flush()

        for user_id in [user1_id, user2_id]:
            participant = ConversationParticipant(
                conversation_id=new_conversation.id,
                user_id=user_id,
                joined_at=now,
            )
            self.db.add(participant)

        await self.db.flush()
        return new_conversation.id

    async def _get_meeting_location_from_offer(
        self, offer_type: str, offer_id: int
    ) -> str:
        if offer_type == "book_offer":
            result = await self.db.execute(
                select(BookOffer).where(BookOffer.id == offer_id)
            )
            offer = result.scalar_one_or_none()
            if offer and offer.location_district:
                return f"{offer.location_district}, Münster"
        return "Münster"

    async def _reserve_book_offer(
        self, offer_id: int, user_id: int, until: datetime
    ) -> None:
        result = await self.db.execute(
            select(BookOffer).where(BookOffer.id == offer_id)
        )
        book_offer = result.scalar_one_or_none()
        if book_offer:
            book_offer.reserved_until = until
            book_offer.reserved_by_user_id = user_id
            book_offer.is_available = False
            logger.info(
                f"Reserved book offer {offer_id} for user {user_id} until {until}"
            )

    async def _unreserve_book_offer(self, offer_id: int) -> None:
        result = await self.db.execute(
            select(BookOffer).where(BookOffer.id == offer_id)
        )
        book_offer = result.scalar_one_or_none()
        if book_offer:
            book_offer.reserved_until = None
            book_offer.reserved_by_user_id = None
            book_offer.is_available = True
            logger.info(f"Unreserved book offer {offer_id}")

    async def _mark_offer_unavailable(self, offer_type: str, offer_id: int) -> None:
        if offer_type == "book_offer":
            result = await self.db.execute(
                select(BookOffer).where(BookOffer.id == offer_id)
            )
            offer = result.scalar_one_or_none()
            if offer:
                offer.is_available = False
                offer.reserved_until = None
                offer.reserved_by_user_id = None
                logger.info(
                    f"Marked book offer {offer_id} as unavailable (transaction completed)"
                )

    async def _transfer_credits(self, transaction: ExchangeTransaction) -> None:
        if transaction.credit_transferred:
            return

        result = await self.db.execute(
            select(User).where(
                User.id.in_([transaction.requester_id, transaction.provider_id])
            )
        )
        users = {u.id: u for u in result.scalars().all()}

        requester = users[transaction.requester_id]
        provider = users[transaction.provider_id]

        if requester.book_credits_remaining < transaction.credit_amount:
            raise HTTPException(status_code=400, detail="Insufficient credits")

        requester.book_credits_remaining -= transaction.credit_amount
        provider.book_credits_remaining += transaction.credit_amount
        transaction.credit_transferred = True

        logger.info(
            f"Credits transferred: {transaction.credit_amount} from {requester.id} to {provider.id}"
        )

    def _build_metadata(
        self,
        data: TransactionCreate,
        offer_info: OfferInfo,
        proposed_by_user_id: int | None = None,
    ) -> dict[str, str | int | bool | list[str] | None]:
        metadata: dict[str, str | int | bool | list[str] | None] = {
            "offer_title": offer_info["title"],
            "offer_condition": offer_info.get("condition"),
            "initial_message": data.initial_message,
        }
        if proposed_by_user_id is not None:
            metadata["proposed_by_user_id"] = proposed_by_user_id
        return metadata

    async def _build_transaction_data(
        self,
        transaction: ExchangeTransaction,
        current_user_id: int,
    ) -> TransactionData:
        offer_info = await self._get_offer_info(
            transaction.offer_type, transaction.offer_id
        )

        result = await self.db.execute(
            select(User).where(
                User.id.in_([transaction.requester_id, transaction.provider_id])
            )
        )
        users = {u.id: u for u in result.scalars().all()}

        proposed_by = transaction.transaction_metadata.get("proposed_by_user_id")
        can_update = transaction.can_be_updated()

        return TransactionData(
            transaction_id=transaction.id,
            transaction_type=ModelTransactionType(transaction.transaction_type),
            status=ModelTransactionStatus(transaction.status),
            offer=TransactionOfferInfo(
                title=offer_info["title"],
                thumbnail_url=offer_info["thumbnail_url"],
                condition=offer_info["condition"],
            ),
            requester=TransactionParticipantInfo(
                id=transaction.requester_id,
                display_name=users[transaction.requester_id].display_name,
                avatar_url=users[transaction.requester_id].profile_image_url,
            ),
            provider=TransactionParticipantInfo(
                id=transaction.provider_id,
                display_name=users[transaction.provider_id].display_name,
                avatar_url=users[transaction.provider_id].profile_image_url,
            ),
            proposed_times=serialize_datetime_list(transaction.proposed_times),
            confirmed_time=serialize_datetime(transaction.confirmed_time),
            exact_address=transaction.exact_address,
            requester_confirmed=transaction.requester_confirmed_handover,
            provider_confirmed=transaction.provider_confirmed_handover,
            created_at=transaction.created_at,
            expires_at=transaction.expires_at,
            can_propose_time=can_update
            and transaction.status == ModelTransactionStatus.PENDING,
            can_confirm_time=can_update
            and transaction.status == ModelTransactionStatus.PENDING
            and len(transaction.proposed_times) > 0
            and proposed_by is not None
            and proposed_by != current_user_id,
            can_confirm_handover=can_update
            and transaction.status == ModelTransactionStatus.TIME_CONFIRMED,
            can_cancel=can_update
            and transaction.status
            in (ModelTransactionStatus.PENDING, ModelTransactionStatus.TIME_CONFIRMED),
        )
