import os
import asyncio
from datetime import datetime, timezone
from typing import Literal
import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID


class TelegramNotifier:
    @staticmethod
    async def send_message(
        message: str,
        level: Literal["info", "warning", "error", "critical"] = "info",
        parse_mode: str = "HTML",
    ) -> bool:
        if not TELEGRAM_ENABLED:
            print(f"📱 [DEV] Telegram notification: [{level.upper()}] {message}")
            return False

        emoji_map = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}

        formatted_message = f"{emoji_map[level]} <b>{level.upper()}</b>\n\n{message}"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": formatted_message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                return response.status_code == 200
        except Exception as e:
            print(f"❌ Failed to send Telegram notification: {e}")
            return False

    @staticmethod
    async def notify_new_user(email: str, display_name: str, user_id: int):
        message = (
            f"🎉 <b>Neue Registrierung</b>\n\n"
            f"👤 <b>Name:</b> {display_name}\n"
            f"📧 <b>Email:</b> {email}\n"
            f"🆔 <b>User ID:</b> {user_id}\n"
            f"🕐 <b>Zeit:</b> {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"
        )
        await TelegramNotifier.send_message(message, level="info")

    @staticmethod
    async def notify_error(
        error_type: str,
        error_message: str,
        user_id: int | None = None,
        user_email: str | None = None,
        endpoint: str | None = None,
        traceback: str | None = None,
    ):
        message = (
            f"💥 <b>Backend Error</b>\n\n"
            f"🔴 <b>Type:</b> <code>{error_type}</code>\n"
            f"📝 <b>Message:</b> {error_message}\n"
        )

        if endpoint:
            message += f"🌐 <b>Endpoint:</b> <code>{endpoint}</code>\n"

        if user_id:
            message += f"👤 <b>User ID:</b> {user_id}\n"

        if user_email:
            message += f"📧 <b>Email:</b> {user_email}\n"

        message += f"🕐 <b>Zeit:</b> {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}\n"

        if traceback and len(traceback) < 500:
            message += f"\n📋 <b>Traceback:</b>\n<pre>{traceback[:500]}</pre>"

        await TelegramNotifier.send_message(message, level="error")

    @staticmethod
    async def notify_critical(
        event: str,
        details: str,
    ):
        message = (
            f"🚨 <b>CRITICAL EVENT</b>\n\n"
            f"⚡ <b>Event:</b> {event}\n"
            f"📝 <b>Details:</b> {details}\n"
            f"🕐 <b>Zeit:</b> {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"
        )
        await TelegramNotifier.send_message(message, level="critical")

    @staticmethod
    async def notify_rate_limit_exceeded(
        limit_type: str,
        ip_address: str,
        user_id: int | None = None,
        attempts: int = 0,
    ):
        message = (
            f"⏱️ <b>Rate Limit Exceeded</b>\n\n"
            f"🔒 <b>Type:</b> {limit_type}\n"
            f"🌐 <b>IP:</b> <code>{ip_address}</code>\n"
            f"📊 <b>Attempts:</b> {attempts}\n"
        )

        if user_id:
            message += f"👤 <b>User ID:</b> {user_id}\n"

        message += f"🕐 <b>Zeit:</b> {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"

        await TelegramNotifier.send_message(message, level="warning")

    @staticmethod
    async def notify_suspicious_activity(
        activity_type: str,
        ip_address: str,
        user_id: int | None = None,
        details: str | None = None,
    ):
        message = (
            f"🕵️ <b>Suspicious Activity</b>\n\n"
            f"⚠️ <b>Type:</b> {activity_type}\n"
            f"🌐 <b>IP:</b> <code>{ip_address}</code>\n"
        )

        if user_id:
            message += f"👤 <b>User ID:</b> {user_id}\n"

        if details:
            message += f"📝 <b>Details:</b> {details}\n"

        message += f"🕐 <b>Zeit:</b> {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"

        await TelegramNotifier.send_message(message, level="warning")


def notify_telegram(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(coro)
        else:
            loop.run_until_complete(coro)
    except Exception as e:
        print(f"❌ Error scheduling Telegram notification: {e}")
