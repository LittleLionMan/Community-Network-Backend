from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..utils.datetime_utils import serialize_datetime, serialize_datetime_list
from .base import Base
from .types import UTCDateTime

type JSONValue = str | int | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


class TransactionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    TIME_CONFIRMED = "time_confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TransactionType(str, Enum):
    BOOK_EXCHANGE = "book_exchange"
    SERVICE_MEETUP = "service_meetup"
    EVENT_CONFIRMATION = "event_confirmation"


class ExchangeTransaction(Base):
    __tablename__ = "exchange_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    transaction_type: Mapped[TransactionType] = mapped_column(
        String(30), nullable=False
    )

    offer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    offer_id: Mapped[int] = mapped_column(Integer, nullable=False)

    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[TransactionStatus] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    time_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    proposed_times: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    confirmed_time: Mapped[datetime | None] = mapped_column(UTCDateTime)

    requester_confirmed_handover: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_confirmed_handover: Mapped[bool] = mapped_column(Boolean, default=False)

    credit_amount: Mapped[int] = mapped_column(Integer, default=1)
    credit_transferred: Mapped[bool] = mapped_column(Boolean, default=False)

    exact_address: Mapped[str | None] = mapped_column(String(500))

    transaction_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False
    )

    message: Mapped["Message"] = relationship("Message", back_populates="transaction")
    requester: Mapped["User"] = relationship(
        "User", foreign_keys=[requester_id], backref="transactions_requested"
    )
    provider: Mapped["User"] = relationship(
        "User", foreign_keys=[provider_id], backref="transactions_provided"
    )

    __table_args__ = (
        Index("idx_transaction_message", "message_id"),
        Index("idx_transaction_offer", "offer_type", "offer_id"),
        Index("idx_transaction_requester", "requester_id", "status"),
        Index("idx_transaction_provider", "provider_id", "status"),
        Index("idx_transaction_status", "status"),
        Index("idx_transaction_expires", "expires_at"),
    )

    def is_participant(self, user_id: int) -> bool:
        return user_id in (self.requester_id, self.provider_id)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def can_be_updated(self) -> bool:
        return (
            self.status
            in (
                TransactionStatus.PENDING,
                TransactionStatus.ACCEPTED,
                TransactionStatus.TIME_CONFIRMED,
            )
            and not self.is_expired()
        )

    def to_flat_transaction_data(self) -> dict[str, str | int | bool | None]:
        proposed_times_str = ",".join(serialize_datetime_list(self.proposed_times))

        return {
            "transaction_id": self.id,
            "transaction_type": self.transaction_type.value,
            "offer_type": self.offer_type,
            "offer_id": self.offer_id,
            "status": self.status.value,
            "requester_id": self.requester_id,
            "provider_id": self.provider_id,
            "proposed_times": proposed_times_str,
            "confirmed_time": serialize_datetime(self.confirmed_time),
            "exact_address": self.exact_address
            if self.status
            in (TransactionStatus.TIME_CONFIRMED, TransactionStatus.COMPLETED)
            else None,
            "requester_confirmed": self.requester_confirmed_handover,
            "provider_confirmed": self.provider_confirmed_handover,
            "created_at": serialize_datetime(self.created_at),
            "updated_at": serialize_datetime(self.time_confirmed_at or self.created_at),
            "expires_at": serialize_datetime(self.expires_at),
            "offer_title": str(self.transaction_metadata.get("offer_title", "")),
        }

    def to_transaction_data(self) -> dict[str, JSONValue]:
        proposed_times_iso = serialize_datetime_list(self.proposed_times)

        return {
            "transaction_id": self.id,
            "transaction_type": self.transaction_type.value,
            "offer_type": self.offer_type,
            "offer_id": self.offer_id,
            "status": self.status.value,
            "requester_id": self.requester_id,
            "provider_id": self.provider_id,
            "proposed_times": cast(list[JSONValue], proposed_times_iso),
            "confirmed_time": serialize_datetime(self.confirmed_time),
            "exact_address": self.exact_address
            if self.status
            in (TransactionStatus.TIME_CONFIRMED, TransactionStatus.COMPLETED)
            else None,
            "requester_confirmed": self.requester_confirmed_handover,
            "provider_confirmed": self.provider_confirmed_handover,
            "created_at": serialize_datetime(self.created_at),
            "updated_at": serialize_datetime(self.time_confirmed_at or self.created_at),
            "expires_at": serialize_datetime(self.expires_at),
            "metadata": self.transaction_metadata,
        }
