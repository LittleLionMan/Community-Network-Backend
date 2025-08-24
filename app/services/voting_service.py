from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..models.poll import Poll, PollOption, Vote
from ..models.user import User
from datetime import datetime

class VotingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_poll_results(self, poll_id: int) -> Dict[str, Any]:

        result = await self.db.execute(
            select(Poll).where(Poll.id == poll_id)
        )
        poll = result.scalar_one_or_none()

        if not poll:
            return {}

        vote_data = await self.db.execute(
            select(
                PollOption.id,
                PollOption.text,
                func.count(Vote.id).label('vote_count')
            )
            .select_from(PollOption)
            .outerjoin(Vote, Vote.option_id == PollOption.id)
            .where(PollOption.poll_id == poll_id)
            .group_by(PollOption.id, PollOption.text)
            .order_by(PollOption.order_index)
        )

        options_data = []
        total_votes = 0
        max_votes = 0
        winners = []

        for option_id, text, count in vote_data:
            vote_count = count or 0
            options_data.append({
                'option_id': option_id,
                'text': text,
                'votes': vote_count,
                'percentage': 0.0
            })
            total_votes += vote_count

            if vote_count > max_votes:
                max_votes = vote_count
                winners = [{'option_id': option_id, 'text': text}]
            elif vote_count == max_votes and max_votes > 0:
                winners.append({'option_id': option_id, 'text': text})

        for option in options_data:
            option['percentage'] = (option['votes'] / max(1, total_votes)) * 100

        result_type = "no_votes"
        if total_votes > 0:
            if len(winners) == 1:
                result_type = "clear_winner"
            elif len(winners) > 1:
                result_type = "tie"
            else:
                result_type = "unclear"

        return {
            'poll_id': poll_id,
            'question': poll.question,
            'total_votes': total_votes,
            'options': options_data,
            'winners': winners,
            'result_type': result_type,
            'is_concluded': poll.ends_at and poll.ends_at < datetime.now() if poll.ends_at else False,  # ✅ Fixed datetime import
            'participation_rate': self._calculate_participation_rate(total_votes)
        }

    def _calculate_participation_rate(self, votes: int) -> str:
        """Simple participation assessment"""
        if votes == 0:
            return "no_participation"
        elif votes < 5:
            return "low"
        elif votes < 20:
            return "moderate"
        else:
            return "high"

    async def get_user_voting_stats(self, user_id: int) -> Dict[str, Any]:

        polls_created_result = await self.db.execute(
            select(func.count(Poll.id)).where(Poll.creator_id == user_id)
        )
        polls_created = polls_created_result.scalar() or 0

        votes_cast_result = await self.db.execute(
            select(func.count(Vote.id)).where(Vote.user_id == user_id)
        )
        votes_cast = votes_cast_result.scalar() or 0

        return {
            'user_id': user_id,
            'polls_created': polls_created,
            'votes_cast': votes_cast,
            'engagement_level': self._assess_engagement(polls_created, votes_cast)
        }

    def _assess_engagement(self, polls_created: int, votes_cast: int) -> str:
        total_activity = polls_created * 2 + votes_cast

        if total_activity == 0:
            return "inactive"
        elif total_activity < 5:
            return "low"
        elif total_activity < 15:
            return "moderate"
        else:
            return "high"

    async def suggest_poll_duration(self, poll_type: str, expected_participants: Optional[int] = None) -> int:
        """Suggest optimal poll duration in hours"""

        if poll_type == "admin":
            return 168
        elif poll_type == "thread":
            if expected_participants and expected_participants > 50:
                return 72
            else:
                return 48

        return 48
