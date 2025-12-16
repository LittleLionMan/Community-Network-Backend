import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forum import ForumPost, ForumThread
from app.models.notification import Notification
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
    async def create_credit_received_notification(
        db: AsyncSession,
        recipient_id: int,
        sender_id: int,
        credit_amount: int,
        offer_title: str,
        transaction_id: int,
    ):
        sender_result = await db.execute(select(User).where(User.id == sender_id))
        sender = sender_result.scalar_one_or_none()

        if not sender:
            return None

        notification_data = {
            "transaction_id": transaction_id,
            "credit_amount": credit_amount,
            "offer_title": offer_title,
            "sender": UserSummary.model_validate(sender).model_dump(mode="json"),
        }

        notification = Notification(
            user_id=recipient_id,
            type="credit_received",
            data=notification_data,
        )

        db.add(notification)
        await db.flush()
        await db.refresh(notification)

        await websocket_manager.send_to_user(
            recipient_id,
            {
                "type": "credit_received",
                "notification_id": notification.id,
                "transaction_id": transaction_id,
                "credit_amount": credit_amount,
                "offer_title": offer_title,
                "message": f"Du hast {credit_amount} Credit{'s' if credit_amount != 1 else ''} für '{offer_title}' erhalten",
                "sender": notification_data["sender"],
            },
        )

        return notification

    @staticmethod
    async def create_credit_spent_notification(
        db: AsyncSession,
        spender_id: int,
        recipient_id: int,
        credit_amount: int,
        offer_title: str,
        transaction_id: int,
    ):
        recipient_result = await db.execute(select(User).where(User.id == recipient_id))
        recipient = recipient_result.scalar_one_or_none()

        if not recipient:
            return None

        notification_data = {
            "transaction_id": transaction_id,
            "credit_amount": credit_amount,
            "offer_title": offer_title,
            "recipient": UserSummary.model_validate(recipient).model_dump(mode="json"),
        }

        notification = Notification(
            user_id=spender_id,
            type="credit_spent",
            data=notification_data,
        )

        db.add(notification)
        await db.flush()
        await db.refresh(notification)

        await websocket_manager.send_to_user(
            spender_id,
            {
                "type": "credit_spent",
                "notification_id": notification.id,
                "transaction_id": transaction_id,
                "credit_amount": credit_amount,
                "offer_title": offer_title,
                "message": f"Du hast {credit_amount} Credit{'s' if credit_amount != 1 else ''} für '{offer_title}' ausgegeben",
                "recipient": notification_data["recipient"],
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
