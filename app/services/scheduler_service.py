from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import logging

from app.database import AsyncSessionLocal
from app.services.event_service import EventService

logger = logging.getLogger(__name__)

class SchedulerService:
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

                await db.execute(
                    delete(RefreshToken).where(RefreshToken.expires_at < cutoff_date)
                )
                await db.execute(
                    delete(EmailVerificationToken).where(EmailVerificationToken.expires_at < cutoff_date)
                )
                await db.execute(
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

                # Find events that ended more than 1 hour ago
                cutoff_time = datetime.now() - timedelta(hours=1)

                result = await db.execute(
                    select(Event).where(
                        Event.end_datetime < cutoff_time,
                        Event.is_active == True
                    ).limit(10)
                )
                events = result.scalars().all()

                event_service = EventService(db)
                processed = 0

                for event in events:
                    result = await event_service.auto_mark_attendance(event.id)
                    if result["success"]:
                        processed += 1

                logger.info(f"✅ Processed {processed} events for attendance")

            except Exception as e:
                logger.error(f"❌ Event attendance processing failed: {e}")

scheduler_service = SchedulerService()
