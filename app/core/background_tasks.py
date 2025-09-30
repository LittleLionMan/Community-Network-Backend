import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from ..database import get_db
from ..models.auth import EmailVerificationToken, PasswordResetToken
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
                            extra={"health_report": health_report}
                        )

                await asyncio.sleep(1800)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Rate limit monitoring error: {e}")
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
                        f"Token cleanup completed: " +
                        f"{refresh_count} refresh, " +
                        f"{email_count} email verification, " +
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

    async def run_maintenance_now(self):
        logger.info("Running manual maintenance...")
        await self._cleanup_expired_tokens()
        try:
            health_report = await run_rate_limit_monitoring()
            if health_report is not None:
                logger.info(f"Rate limiting health: {health_report['health_score']}/100")
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
