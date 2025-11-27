import logging
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.message import Message
from app.models.user import User
from app.schemas.transaction import (
    TransactionAccept,
    TransactionCancel,
    TransactionConfirmHandover,
    TransactionConfirmTime,
    TransactionCreate,
    TransactionData,
    TransactionHistoryItem,
    TransactionOfferInfo,
    TransactionParticipantInfo,
    TransactionProposeTime,
    TransactionReject,
)
from app.schemas.transaction import (
    TransactionStatus as SchemaTransactionStatus,
)
from app.schemas.transaction import (
    TransactionType as SchemaTransactionType,
)

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

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)

        transaction = ExchangeTransaction(
            transaction_type=ModelTransactionType(data.transaction_type.value),
            offer_type=data.offer_type,
            offer_id=data.offer_id,
            requester_id=requester_id,
            provider_id=provider_id,
            status=ModelTransactionStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            proposed_times=data.proposed_times,
            exact_address=offer_info.get("location_address"),
            transaction_metadata=self._build_metadata(data, offer_info),
        )

        self.db.add(transaction)
        await self.db.flush()

        message = Message(
            conversation_id=conversation_id,
            sender_id=requester_id,
            message_type="transaction_token",
            content=data.initial_message,
            transaction_data=transaction.to_transaction_data(),
            created_at=now,
        )
        self.db.add(message)
        await self.db.flush()

        transaction.message_id = message.id
        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Transaction {transaction.id} created by user {requester_id}")

        return await self._build_transaction_data(transaction, requester_id)

    async def accept_transaction(
        self,
        transaction_id: int,
        user_id: int,
        data: TransactionAccept,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if transaction.provider_id != user_id:
            raise HTTPException(
                status_code=403, detail="Only provider can accept transaction"
            )

        if transaction.status != ModelTransactionStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Transaction cannot be accepted in current state",
            )

        if transaction.is_expired():
            raise HTTPException(status_code=400, detail="Transaction has expired")

        transaction.status = ModelTransactionStatus.ACCEPTED
        transaction.accepted_at = datetime.now(timezone.utc)

        message = await self._get_message(transaction.message_id)
        message.transaction_data = transaction.to_transaction_data()

        if data.message:
            system_message = Message(
                conversation_id=message.conversation_id,
                sender_id=user_id,
                message_type="text",
                content=data.message,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(system_message)

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Transaction {transaction_id} accepted by user {user_id}")

        return await self._build_transaction_data(transaction, user_id)

    async def reject_transaction(
        self,
        transaction_id: int,
        user_id: int,
        data: TransactionReject,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if transaction.provider_id != user_id:
            raise HTTPException(
                status_code=403, detail="Only provider can reject transaction"
            )

        if transaction.status != ModelTransactionStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Transaction cannot be rejected in current state",
            )

        transaction.status = ModelTransactionStatus.REJECTED
        transaction.transaction_metadata["rejection_reason"] = data.reason

        message = await self._get_message(transaction.message_id)
        message.transaction_data = transaction.to_transaction_data()

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Transaction {transaction_id} rejected by user {user_id}")

        return await self._build_transaction_data(transaction, user_id)

    async def propose_time(
        self,
        transaction_id: int,
        user_id: int,
        data: TransactionProposeTime,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        if not transaction.can_be_updated():
            raise HTTPException(status_code=400, detail="Transaction cannot be updated")

        if data.proposed_time in transaction.proposed_times:
            raise HTTPException(status_code=400, detail="Time already proposed")

        if len(transaction.proposed_times) >= 10:
            raise HTTPException(
                status_code=400, detail="Maximum number of proposed times reached"
            )

        transaction.proposed_times = [*transaction.proposed_times, data.proposed_time]

        message = await self._get_message(transaction.message_id)
        message.transaction_data = transaction.to_transaction_data()

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Time proposed for transaction {transaction_id} by user {user_id}")

        return await self._build_transaction_data(transaction, user_id)

    async def confirm_time(
        self,
        transaction_id: int,
        user_id: int,
        data: TransactionConfirmTime,
    ) -> TransactionData:
        transaction = await self._get_transaction_or_404(transaction_id)

        if not transaction.is_participant(user_id):
            raise HTTPException(
                status_code=403, detail="Not a participant in this transaction"
            )

        if not transaction.can_be_updated():
            raise HTTPException(status_code=400, detail="Transaction cannot be updated")

        transaction.status = ModelTransactionStatus.TIME_CONFIRMED
        transaction.confirmed_time = data.confirmed_time
        transaction.exact_address = data.exact_address
        transaction.time_confirmed_at = datetime.now(timezone.utc)

        message = await self._get_message(transaction.message_id)
        message.transaction_data = transaction.to_transaction_data()

        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(
            f"Time confirmed for transaction {transaction_id} by user {user_id}"
        )

        return await self._build_transaction_data(transaction, user_id)

    async def confirm_handover(
        self,
        transaction_id: int,
        user_id: int,
        data: TransactionConfirmHandover,
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

        if data.notes:
            if user_id == transaction.requester_id:
                transaction.transaction_metadata["requester_notes"] = data.notes
            else:
                transaction.transaction_metadata["provider_notes"] = data.notes

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

        message = await self._get_message(transaction.message_id)
        message.transaction_data = transaction.to_transaction_data()

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
        data: TransactionCancel,
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

        if data.reason:
            transaction.transaction_metadata["cancellation_reason"] = data.reason
            transaction.transaction_metadata["cancelled_by"] = str(user_id)

        message = await self._get_message(transaction.message_id)
        message.transaction_data = transaction.to_transaction_data()

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
                    id=t.id,
                    transaction_type=SchemaTransactionType(t.transaction_type.value),
                    status=SchemaTransactionStatus(t.status.value),
                    offer_title=offer_info["title"],
                    offer_thumbnail=offer_info["thumbnail_url"],
                    counterpart_name=other_user.display_name,
                    counterpart_avatar=other_user.profile_image_url,
                    confirmed_time=t.confirmed_time,
                    created_at=t.created_at,
                    updated_at=t.time_confirmed_at or t.created_at,
                )
            )

        return items

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
                select(BookOffer).where(BookOffer.id == offer_id)
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
                        ModelTransactionStatus.ACCEPTED,
                        ModelTransactionStatus.TIME_CONFIRMED,
                    ]
                ),
            )
        )
        return result.scalar_one_or_none()

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

        is_provider = current_user_id == transaction.provider_id
        can_update = transaction.can_be_updated()

        return TransactionData(
            transaction_id=transaction.id,
            transaction_type=SchemaTransactionType(transaction.transaction_type.value),
            status=SchemaTransactionStatus(transaction.status.value),
            offer=TransactionOfferInfo(
                offer_id=transaction.offer_id,
                offer_type=transaction.offer_type,
                title=offer_info["title"],
                thumbnail_url=offer_info["thumbnail_url"],
                condition=offer_info["condition"],
                metadata={},
            ),
            requester=TransactionParticipantInfo(
                id=transaction.requester_id,
                display_name=users[transaction.requester_id].display_name,
                profile_image_url=users[transaction.requester_id].profile_image_url,
            ),
            provider=TransactionParticipantInfo(
                id=transaction.provider_id,
                display_name=users[transaction.provider_id].display_name,
                profile_image_url=users[transaction.provider_id].profile_image_url,
            ),
            proposed_times=transaction.proposed_times,
            confirmed_time=transaction.confirmed_time,
            exact_address=transaction.exact_address
            if transaction.status
            in (ModelTransactionStatus.TIME_CONFIRMED, ModelTransactionStatus.COMPLETED)
            else None,
            requester_confirmed=transaction.requester_confirmed_handover,
            provider_confirmed=transaction.provider_confirmed_handover,
            created_at=transaction.created_at,
            updated_at=transaction.time_confirmed_at or transaction.created_at,
            expires_at=transaction.expires_at,
            is_expired=transaction.is_expired(),
            can_accept=is_provider
            and transaction.status == ModelTransactionStatus.PENDING
            and can_update,
            can_reject=is_provider
            and transaction.status == ModelTransactionStatus.PENDING,
            can_propose_time=can_update
            and transaction.status
            in (ModelTransactionStatus.PENDING, ModelTransactionStatus.ACCEPTED),
            can_confirm_time=can_update
            and transaction.status == ModelTransactionStatus.ACCEPTED,
            can_confirm_handover=can_update
            and transaction.status == ModelTransactionStatus.TIME_CONFIRMED,
            can_cancel=can_update,
            metadata=transaction.transaction_metadata,
        )

    def _build_metadata(
        self,
        data: TransactionCreate,
        offer_info: OfferInfo,
    ) -> dict[str, str | int | bool | list[str] | None]:
        return {
            "offer_title": offer_info["title"],
            "offer_condition": offer_info.get("condition"),
            "initial_message": data.initial_message,
        }

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

    async def _mark_offer_unavailable(self, offer_type: str, offer_id: int) -> None:
        if offer_type == "book_offer":
            result = await self.db.execute(
                select(BookOffer).where(BookOffer.id == offer_id)
            )
            offer = result.scalar_one_or_none()
            if offer:
                offer.is_available = False
                logger.info(f"Marked book offer {offer_id} as unavailable")
