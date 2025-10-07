from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import re

from app.models.notification import Notification
from app.models.forum import ForumPost, ForumThread
from app.models.user import User
from app.schemas.user import UserSummary
from app.services.websocket_service import websocket_manager


def strip_html_tags(html: str) -> str:
    clean = re.sub("<.*?>", "", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


class NotificationService:
    @staticmethod
    async def create_forum_reply_notification(
        db: AsyncSession,
        thread: ForumThread,
        new_post: ForumPost,
        actor: User,
    ):
        if thread.creator_id == actor.id:
            return None

        creator_result = await db.execute(
            select(User).where(User.id == thread.creator_id, User.is_active)
        )
        creator = creator_result.scalar_one_or_none()

        if not creator or not creator.notification_forum_reply:
            return None

        notification_data = {
            "thread_id": thread.id,
            "post_id": new_post.id,
            "thread_title": thread.title,
            "content_preview": strip_html_tags(new_post.content)[:200],
            "actor": UserSummary.model_validate(actor).model_dump(mode="json"),
        }

        notification = Notification(
            user_id=thread.creator_id,
            type="forum_reply",
            data=notification_data,
        )

        db.add(notification)
        await db.flush()
        await db.refresh(notification)

        await websocket_manager.send_to_user(
            thread.creator_id,
            {
                "type": "forum_reply",
                "notification_id": notification.id,
                "thread_id": thread.id,
                "post_id": new_post.id,
                "thread_title": thread.title,
                "message": f"{actor.display_name} hat auf deinen Thread geantwortet",
                "actor": notification_data["actor"],
            },
        )

        return notification

    @staticmethod
    async def create_forum_mention_notifications(
        db: AsyncSession,
        thread: ForumThread,
        post: ForumPost,
        mentioned_user_ids: list[int],
        actor: User,
    ):
        notifications: list[Notification] = []

        for user_id in mentioned_user_ids:
            if user_id == actor.id:
                continue

            result = await db.execute(
                select(User).where(User.id == user_id, User.is_active)
            )
            user = result.scalar_one_or_none()

            if not user or not user.notification_forum_mention:
                continue

            notification_data = {
                "thread_id": thread.id,
                "post_id": post.id,
                "thread_title": thread.title,
                "content_preview": strip_html_tags(post.content)[:200],
                "actor": UserSummary.model_validate(actor).model_dump(mode="json"),
            }

            notification = Notification(
                user_id=user_id,
                type="forum_mention",
                data=notification_data,
            )

            db.add(notification)
            await db.flush()
            await db.refresh(notification)

            notifications.append(notification)

            await websocket_manager.send_to_user(
                user_id,
                {
                    "type": "forum_mention",
                    "notification_id": notification.id,
                    "thread_id": thread.id,
                    "post_id": post.id,
                    "thread_title": thread.title,
                    "message": f"{actor.display_name} hat dich in einem Post erwähnt",
                    "actor": notification_data["actor"],
                },
            )

        return notifications

    @staticmethod
    async def create_forum_quote_notification(
        db: AsyncSession,
        thread: ForumThread,
        new_post: ForumPost,
        quoted_post: ForumPost,
        actor: User,
    ):
        if quoted_post.author_id == actor.id:
            return None

        author_result = await db.execute(
            select(User).where(User.id == quoted_post.author_id, User.is_active)
        )
        author = author_result.scalar_one_or_none()

        if not author or not author.notification_forum_quote:
            return None

        notification_data = {
            "thread_id": thread.id,
            "post_id": new_post.id,
            "quoted_post_id": quoted_post.id,
            "thread_title": thread.title,
            "content_preview": strip_html_tags(new_post.content)[:200],
            "actor": UserSummary.model_validate(actor).model_dump(mode="json"),
        }

        notification = Notification(
            user_id=quoted_post.author_id,
            type="forum_quote",
            data=notification_data,
        )

        db.add(notification)
        await db.flush()
        await db.refresh(notification)

        await websocket_manager.send_to_user(
            quoted_post.author_id,
            {
                "type": "forum_quote",
                "notification_id": notification.id,
                "thread_id": thread.id,
                "post_id": new_post.id,
                "quoted_post_id": quoted_post.id,
                "thread_title": thread.title,
                "message": f"{actor.display_name} hat deinen Post zitiert",
                "actor": notification_data["actor"],
            },
        )

        return notification

    @staticmethod
    async def delete_notifications_for_post(db: AsyncSession, post_id: int):
        from sqlalchemy import delete

        _ = await db.execute(
            delete(Notification).where(
                Notification.data["post_id"].astext == str(post_id)
            )
        )

        await db.commit()
