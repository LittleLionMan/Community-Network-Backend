from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import re
from typing import TypedDict

from ..models.comment import Comment
from ..models.forum import ForumPost


class ModerationResult(TypedDict):
    is_flagged: bool
    reasons: list[str]
    confidence: float
    requires_review: bool


class ModerationService:
    db: AsyncSession
    banned_words: set[str]
    suspicious_patterns: list[str]

    def __init__(self, db: AsyncSession):
        self.db = db

        self.banned_words = {
            "Fotze",
            "Hurensohn",
        }

        self.suspicious_patterns = [
            r"\b(?:https?://|www\.)\S+",
            r"\b\d{10,}\b",
            r"[A-Z]{5,}",
            r"(.)\1{4,}",
        ]

    def check_content(self, text: str) -> ModerationResult:
        if not text:
            return {
                "is_flagged": False,
                "reasons": [],
                "confidence": 0.0,
                "requires_review": False,
            }

        text_lower = text.lower()
        reasons: list[str] = []
        confidence = 0.0

        for word in self.banned_words:
            if word in text_lower:
                reasons.append(f"Contains banned word: {word}")
                confidence += 0.8

        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                if "http" in pattern:
                    reasons.append("Contains URL")
                    confidence += 0.3
                elif "digit" in pattern:
                    reasons.append("Contains phone number")
                    confidence += 0.5
                elif "A-Z" in pattern:
                    reasons.append("Excessive caps")
                    confidence += 0.2
                else:
                    reasons.append("Suspicious pattern detected")
                    confidence += 0.3

        if len(text) > 2000:
            reasons.append("Unusually long text")
            confidence += 0.1

        words = text_lower.split()
        if len(words) > 10:
            word_count: dict[str, int] = {}
            for word in words:
                word_count[word] = word_count.get(word, 0) + 1

            max_repetitions = max(word_count.values()) if word_count else 0
            if max_repetitions > len(words) * 0.3:
                reasons.append("Excessive word repetition")
                confidence += 0.4

        is_flagged = confidence > 0.7
        requires_review = confidence > 0.3

        return {
            "is_flagged": is_flagged,
            "reasons": reasons,
            "confidence": min(confidence, 1.0),
            "requires_review": requires_review,
        }

    async def moderate_user_content(self, user_id: int) -> dict[str, object]:
        recent_comments = await self.db.execute(
            select(Comment)
            .where(Comment.author_id == user_id)
            .order_by(Comment.created_at.desc())
            .limit(50)
        )
        comments = recent_comments.scalars().all()

        recent_posts = await self.db.execute(
            select(ForumPost)
            .where(ForumPost.author_id == user_id)
            .order_by(ForumPost.created_at.desc())
            .limit(20)
        )
        posts = recent_posts.scalars().all()

        flagged_content: list[dict[str, object]] = []
        total_confidence: float = 0.0
        total_items: int = 0

        for comment in comments:
            result = self.check_content(comment.content)
            if result["requires_review"]:
                flagged_content.append(
                    {
                        "type": "comment",
                        "id": comment.id,
                        "content_preview": comment.content[:100],
                        "moderation": result,
                    }
                )
            confidence_value = result.get("confidence", 0.0)
            if isinstance(confidence_value, (int, float)):
                total_confidence += float(confidence_value)
            total_items += 1

        for post in posts:
            result = self.check_content(post.content)
            if result["requires_review"]:
                flagged_content.append(
                    {
                        "type": "forum_post",
                        "id": post.id,
                        "content_preview": post.content[:100],
                        "moderation": result,
                    }
                )
            confidence_value = result.get("confidence", 0.0)
            if isinstance(confidence_value, (int, float)):
                total_confidence += float(confidence_value)
            total_items += 1

        avg_confidence = total_confidence / max(1, total_items)

        return {
            "user_id": user_id,
            "flagged_items": len(flagged_content),
            "total_items_checked": total_items,
            "average_risk_score": avg_confidence,
            "needs_admin_review": len(flagged_content) > 3 or avg_confidence > 0.5,
            "flagged_content": flagged_content,
        }

    async def get_moderation_queue(self) -> list[dict[str, object]]:
        return [
            {
                "id": 1,
                "content_type": "comment",
                "content_id": 123,
                "user_id": 456,
                "reason": "Contains suspicious patterns",
                "confidence": 0.8,
                "created_at": "2024-01-15T10:30:00Z",
                "status": "pending",
            }
        ]
