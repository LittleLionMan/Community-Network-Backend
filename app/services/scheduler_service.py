from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from sqlalchemy import update
from app.models.message import Message

from app.database import AsyncSessionLocal
from app.services.event_service import EventService
from ..services.websocket_service import websocket_manager


logger = logging.getLogger(__name__)

class SchedulerService:
    scheduler: AsyncIOScheduler

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        if self.scheduler.running:
            return

        self.scheduler.add_job(
            func=self.daily_cleanup,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_cleanup",
            replace_existing=True
        )

        self.scheduler.add_job(
            func=self.process_event_attendance,
            trigger=CronTrigger(minute=0),
            id="event_attendance",
            replace_existing=True
        )

        self.scheduler.add_job(
            func=self.weekly_message_analytics_cleanup,
            trigger=CronTrigger(day_of_week=6, hour=4, minute=0),
            id="weekly_message_analytics_cleanup",
            replace_existing=True
        )

        self.scheduler.add_job(
            func=lambda: websocket_manager.cleanup_old_typing_status(10),
            trigger='interval',
            seconds=30,
            id='websocket_typing_cleanup',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("🕒 Scheduler started with background jobs")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("🕒 Scheduler stopped")

    async def daily_cleanup(self):
        logger.info("🧹 Starting daily cleanup...")

        async with AsyncSessionLocal() as db:
            try:
                from app.models.auth import RefreshToken, EmailVerificationToken, PasswordResetToken
                from app.models.user import User
                from sqlalchemy import delete, select

                cutoff_date = datetime.now() - timedelta(days=30)

                _ = await db.execute(
                    delete(RefreshToken).where(RefreshToken.expires_at < cutoff_date)
                )
                _ = await db.execute(
                    delete(EmailVerificationToken).where(EmailVerificationToken.expires_at < cutoff_date)
                )
                _ = await db.execute(
                    delete(PasswordResetToken).where(PasswordResetToken.expires_at < cutoff_date)
                )
                user_cutoff_date = datetime.now() - timedelta(days=30)
                result = await db.execute(
                    select(User).where(
                        User.email_verified == False,
                        User.created_at < user_cutoff_date
                    )
                )
                unverified_users = result.scalars().all()

                deleted_count = 0
                for user in unverified_users:
                    await db.delete(user)
                    deleted_count += 1

                await db.commit()
                if deleted_count > 0:
                    logger.info(f"🗑️ Deleted {deleted_count} unverified accounts older than 30 days")

                await self._cleanup_message_system()
                websocket_manager.cleanup_old_typing_status()

                logger.info("✅ Daily cleanup completed")

            except Exception as e:
                logger.error(f"❌ Daily cleanup failed: {e}")
                await db.rollback()

    async def process_event_attendance(self):
        logger.info("🎪 Processing event attendance...")

        async with AsyncSessionLocal() as db:
            try:
                from app.models.event import Event
                from sqlalchemy import select

                cutoff_time = datetime.now() - timedelta(hours=1)

                result = await db.execute(
                    select(Event).where(
                        Event.end_datetime < cutoff_time,
                        Event.is_active == True
                    ).limit(10)
                )
                events: list[Event] = list(result.scalars().all())

                event_service = EventService(db)
                processed = 0

                for event in events:
                    result = await event_service.auto_mark_attendance(event.id)
                    if result.get("success", False):
                        processed += 1

                logger.info(f"✅ Processed {processed} events for attendance")

            except Exception as e:
                logger.error(f"❌ Event attendance processing failed: {e}")


    async def _cleanup_message_system(self):
        try:
            from app.services.message_service import MessageService

            async with AsyncSessionLocal() as db:
                message_service = MessageService(db)

                old_messages_count = await message_service.cleanup_old_messages(365)
                if old_messages_count > 0:
                    logger.info(f"🗑️ Cleaned up {old_messages_count} old deleted messages")

                empty_conversations_count = await message_service.cleanup_empty_conversations()
                if empty_conversations_count > 0:
                    logger.info(f"🗑️ Cleaned up {empty_conversations_count} empty conversations")

        except Exception as e:
            logger.error(f"❌ Message system cleanup failed: {e}")

    async def weekly_message_analytics_cleanup(self):
        try:
            logger.info("🧹 Starting weekly message analytics cleanup...")

            async with AsyncSessionLocal() as db:

                cutoff_date = datetime.now() - timedelta(days=180)

                _ = await db.execute(
                    update(Message)
                    .where(
                        Message.moderated_at < cutoff_date,
                        Message.moderation_status == 'approved'
                    )
                    .values(
                        moderation_reason=None,
                        moderated_at=None,
                        moderated_by=None
                    )
                )

                await db.commit()
                logger.info("✅ Weekly message analytics cleanup completed")

        except Exception as e:
            logger.error(f"❌ Weekly message analytics cleanup failed: {e}")

    def setup_message_cleanup_jobs(self):
        try:
            self.scheduler.add_job(
                self._cleanup_message_system,
                'cron',
                hour=3,
                minute=0,
                id='daily_message_cleanup',
                replace_existing=True
            )

            self.scheduler.add_job(
                self.weekly_message_analytics_cleanup,
                'cron',
                day_of_week=6,
                hour=4,
                minute=0,
                id='weekly_message_analytics_cleanup',
                replace_existing=True
            )

            self.scheduler.add_job(
                lambda: websocket_manager.cleanup_old_typing_status(10),
                'interval',
                seconds=30,
                id='websocket_typing_cleanup',
                replace_existing=True
            )

            logger.info("Message cleanup jobs scheduled successfully")

        except Exception as e:
            logger.error(f"Failed to schedule message cleanup jobs: {e}")

scheduler_service = SchedulerService()
