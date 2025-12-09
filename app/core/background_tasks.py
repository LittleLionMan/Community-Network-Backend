import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.auth import EmailVerificationToken, PasswordResetToken
from ..models.exchange_transaction import ExchangeTransaction, TransactionStatus
from ..services.auth import AuthService
from .monitoring import run_rate_limit_monitoring

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    running: bool
    tasks: list[asyncio.Task[None]]

    def __init__(self):
        self.running = False
        self.tasks = []

    async def start(self):
        if self.running:
            return

        self.running = True
        logger.info("Starting background tasks...")

        task1 = asyncio.create_task(self._token_cleanup_loop())
        self.tasks.append(task1)

        task2 = asyncio.create_task(self._monitoring_loop())
        self.tasks.append(task2)

        task3 = asyncio.create_task(self._transaction_cleanup_loop())
        self.tasks.append(task3)

        logger.info(f"Started {len(self.tasks)} background tasks")

    async def stop(self):
        if not self.running:
            return

        self.running = False
        logger.info("Stopping background tasks...")

        for task in self.tasks:
            _ = task.cancel()

        _ = await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

        logger.info("All background tasks stopped")

    async def _token_cleanup_loop(self):
        while self.running:
            try:
                await self._cleanup_expired_tokens()
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Token cleanup error: {e}")
                await asyncio.sleep(300)

    async def _monitoring_loop(self):
        while self.running:
            try:
                health_report = await run_rate_limit_monitoring()

                if health_report:
                    health_score = health_report.get("health_score")
                    if isinstance(health_score, (int, float)) and health_score < 60:
                        logger.warning(
                            f"Rate limiting health degraded: {health_score}/100",
                            extra={"health_report": health_report},
                        )

                await asyncio.sleep(1800)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Rate limit monitoring error: {e}")
                await asyncio.sleep(600)

    async def _transaction_cleanup_loop(self):
        """Cleanup expired transactions every hour."""
        while self.running:
            try:
                await self._cleanup_expired_transactions()
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Transaction cleanup error: {e}")
                await asyncio.sleep(600)

    async def _cleanup_expired_tokens(self):
        async for db in get_db():
            try:
                auth_service = AuthService(db)
                refresh_count = await auth_service.cleanup_expired_tokens()
                email_count = await self._cleanup_expired_email_tokens(db)
                reset_count = await self._cleanup_expired_reset_tokens(db)

                total_cleaned = refresh_count + email_count + reset_count

                if total_cleaned > 0:
                    logger.info(
                        f"Token cleanup completed: "
                        f"{refresh_count} refresh, "
                        f"{email_count} email verification, "
                        f"{reset_count} password reset tokens cleaned"
                    )

            except Exception as e:
                logger.error(f"Database cleanup error: {e}")
                await db.rollback()
            finally:
                await db.close()

    async def _cleanup_expired_email_tokens(self, db: AsyncSession) -> int:
        result = await db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.expires_at < datetime.now(timezone.utc)
            )
        )
        await db.commit()
        return result.rowcount

    async def _cleanup_expired_reset_tokens(self, db: AsyncSession) -> int:
        result = await db.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.expires_at < datetime.now(timezone.utc)
            )
        )
        await db.commit()
        return result.rowcount

    async def _cleanup_expired_transactions(self):
        async for db in get_db():
            try:
                now = datetime.now(timezone.utc)

                pending_expired = await self._expire_pending_transactions(db, now)

                unconfirmed_past = await self._expire_unconfirmed_meetings(db, now)

                total_cleaned = pending_expired + unconfirmed_past

                if total_cleaned > 0:
                    logger.info(
                        f"Transaction cleanup completed: "
                        f"{pending_expired} expired pending, "
                        f"{unconfirmed_past} unconfirmed past meetings"
                    )

            except Exception as e:
                logger.error(f"Transaction cleanup error: {e}")
                await db.rollback()
            finally:
                await db.close()

    async def _expire_pending_transactions(
        self, db: AsyncSession, now: datetime
    ) -> int:
        from ..services.availability_service import AvailabilityService

        query = select(ExchangeTransaction).where(
            and_(
                ExchangeTransaction.status == TransactionStatus.PENDING,
                ExchangeTransaction.expires_at < now,
            )
        )

        result = await db.execute(query)
        expired_transactions = result.scalars().all()

        count = 0
        for transaction in expired_transactions:
            transaction.status = TransactionStatus.EXPIRED

            if transaction.offer_type == "book_offer":
                await self._unreserve_book_offer(db, transaction.offer_id)

            await AvailabilityService.remove_transaction_blocks(
                db=db,
                transaction_id=transaction.id,
            )

            count += 1

        if count > 0:
            await db.commit()

        return count

    async def _expire_unconfirmed_meetings(
        self, db: AsyncSession, now: datetime
    ) -> int:
        from ..services.availability_service import AvailabilityService

        cutoff_time = now - timedelta(hours=24)

        query = select(ExchangeTransaction).where(
            and_(
                ExchangeTransaction.status == TransactionStatus.TIME_CONFIRMED,
                ExchangeTransaction.confirmed_time < cutoff_time,
                ~(
                    ExchangeTransaction.requester_confirmed_handover
                    & ExchangeTransaction.provider_confirmed_handover
                ),
            )
        )

        result = await db.execute(query)
        unconfirmed_transactions = result.scalars().all()

        count = 0
        for transaction in unconfirmed_transactions:
            transaction.status = TransactionStatus.EXPIRED

            if transaction.offer_type == "book_offer":
                await self._unreserve_book_offer(db, transaction.offer_id)

            await AvailabilityService.remove_transaction_blocks(
                db=db,
                transaction_id=transaction.id,
            )

            logger.info(
                f"Expired unconfirmed transaction {transaction.id} - "
                f"meeting was at {transaction.confirmed_time}, "
                f"requester_confirmed: {transaction.requester_confirmed_handover}, "
                f"provider_confirmed: {transaction.provider_confirmed_handover}"
            )

            count += 1

        if count > 0:
            await db.commit()

        return count

    async def _unreserve_book_offer(self, db: AsyncSession, offer_id: int):
        """Unreserve a book offer."""
        from ..models.book_offer import BookOffer

        result = await db.execute(select(BookOffer).where(BookOffer.id == offer_id))
        book_offer = result.scalar_one_or_none()

        if book_offer:
            book_offer.reserved_until = None
            book_offer.reserved_by_user_id = None
            book_offer.is_available = True

    async def run_maintenance_now(self):
        logger.info("Running manual maintenance...")
        await self._cleanup_expired_tokens()
        await self._cleanup_expired_transactions()
        try:
            health_report = await run_rate_limit_monitoring()
            if health_report is not None:
                logger.info(
                    f"Rate limiting health: {health_report['health_score']}/100"
                )
        except Exception as e:
            logger.error(f"Monitoring check failed: {e}")
        logger.info("Manual maintenance completed")


background_tasks = BackgroundTaskManager()


async def startup_background_tasks():
    await background_tasks.start()


async def shutdown_background_tasks():
    await background_tasks.stop()


async def run_maintenance():
    await background_tasks.run_maintenance_now()
