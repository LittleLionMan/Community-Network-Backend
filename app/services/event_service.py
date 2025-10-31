from datetime import datetime, timedelta, timezone
from typing import TypedDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from ..models.event import Event, EventParticipation
from ..models.user import User
from ..models.enums import ParticipationStatus


class EventCapacityInfo(TypedDict, total=False):
    has_capacity_limit: bool
    max_participants: int | None
    current_participants: int
    available_spots: int | None
    is_full: bool
    utilization_percentage: float
    error: str


class AutoAttendanceResult(TypedDict, total=False):
    success: bool
    reason: str
    participants_updated: int
    event_title: str


class UserEventHistory(TypedDict, total=False):
    upcoming_events: int
    events_attended: int
    events_cancelled: int
    attendance_rate: float
    total_events: int
    engagement_level: str
    error: str


class EventService:
    db: AsyncSession

    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_join_event(
        self, event: Event | None, user: User | None
    ) -> tuple[bool, str]:
        if not event or not user:
            return False, "Invalid event or user"

        current_time = datetime.now(timezone.utc)
        if not event.start_datetime or event.start_datetime <= current_time:
            return False, "Cannot join past events"

        if not event.is_active:
            return False, "Event is no longer active"

        try:
            result = await self.db.execute(
                select(EventParticipation).where(
                    EventParticipation.event_id == event.id,
                    EventParticipation.user_id == user.id,
                    EventParticipation.status == ParticipationStatus.REGISTERED,
                )
            )
            if result.scalar_one_or_none():
                return False, "Already registered for this event"
        except Exception:
            return False, "Unable to verify registration status"

        if event.max_participants and event.max_participants > 0:
            try:
                result = await self.db.execute(
                    select(func.count(EventParticipation.id)).where(
                        EventParticipation.event_id == event.id,
                        EventParticipation.status == ParticipationStatus.REGISTERED,
                    )
                )
                current_count = result.scalar()

                if current_count is None:
                    current_count = 0

                if current_count >= event.max_participants:
                    return False, "Event is full"

            except Exception:
                pass

        from ..config import settings

        deadline_hours = getattr(settings, "EVENT_REGISTRATION_DEADLINE_HOURS", 24)

        try:
            registration_deadline = event.start_datetime - timedelta(
                hours=deadline_hours
            )
            if current_time > registration_deadline:
                return (
                    False,
                    f"Registration deadline passed ({deadline_hours}h before event)",
                )
        except Exception:
            pass

        return True, "Can join"

    async def get_event_capacity_info(self, event: Event) -> EventCapacityInfo:
        if not event.max_participants:
            return {
                "has_capacity_limit": False,
                "max_participants": None,
                "current_participants": 0,
                "available_spots": None,
                "is_full": False,
            }

        try:
            result = await self.db.execute(
                select(func.count(EventParticipation.id)).where(
                    EventParticipation.event_id == event.id,
                    EventParticipation.status == ParticipationStatus.REGISTERED,
                )
            )
            current_count = result.scalar() or 0

            available_spots = max(0, event.max_participants - current_count)
            is_full = current_count >= event.max_participants

            return {
                "has_capacity_limit": True,
                "max_participants": event.max_participants,
                "current_participants": current_count,
                "available_spots": available_spots,
                "is_full": is_full,
                "utilization_percentage": round(
                    (current_count / event.max_participants) * 100, 1
                ),
            }

        except Exception:
            return {
                "has_capacity_limit": True,
                "max_participants": event.max_participants,
                "current_participants": 0,
                "available_spots": event.max_participants,
                "is_full": False,
                "error": "Could not fetch current capacity",
            }

    async def auto_mark_attendance(self, event_id: int) -> AutoAttendanceResult:
        try:
            event = await self.db.get(Event, event_id)

            if not event:
                return {
                    "success": False,
                    "reason": "Event not found",
                    "participants_updated": 0,
                }

            if not event.end_datetime:
                return {
                    "success": False,
                    "reason": "Event has no end time",
                    "participants_updated": 0,
                }

            from ..config import settings

            delay_hours = getattr(settings, "EVENT_AUTO_ATTENDANCE_DELAY_HOURS", 1)

            cutoff_time = event.end_datetime + timedelta(hours=delay_hours)
            if datetime.now(timezone.utc) < cutoff_time:
                return {
                    "success": False,
                    "reason": f"Event ended less than {delay_hours}h ago",
                    "participants_updated": 0,
                }

            count_result = await self.db.execute(
                select(func.count(EventParticipation.id)).where(
                    EventParticipation.event_id == event_id,
                    EventParticipation.status == ParticipationStatus.REGISTERED,
                )
            )
            participants_to_update = count_result.scalar() or 0

            if participants_to_update == 0:
                return {
                    "success": True,
                    "reason": "No participants to update",
                    "participants_updated": 0,
                }

            result = await self.db.execute(
                update(EventParticipation)
                .where(
                    EventParticipation.event_id == event_id,
                    EventParticipation.status == ParticipationStatus.REGISTERED,
                )
                .values(status=ParticipationStatus.ATTENDED)
            )

            await self.db.commit()
            actual_updated = result.rowcount or 0

            return {
                "success": True,
                "reason": "Auto-attendance processed successfully",
                "participants_updated": actual_updated,
                "event_title": event.title,
            }

        except Exception as e:
            return {
                "success": False,
                "reason": f"Error processing auto-attendance: {str(e)}",
                "participants_updated": 0,
            }

    async def get_user_event_history(self, user_id: int) -> UserEventHistory:
        if not user_id:
            return {
                "upcoming_events": 0,
                "events_attended": 0,
                "events_cancelled": 0,
                "attendance_rate": 0.0,
                "error": "Invalid user ID",
            }

        try:
            result = await self.db.execute(
                select(
                    func.count()
                    .filter(EventParticipation.status == ParticipationStatus.REGISTERED)
                    .label("upcoming"),
                    func.count()
                    .filter(EventParticipation.status == ParticipationStatus.ATTENDED)
                    .label("attended"),
                    func.count()
                    .filter(EventParticipation.status == ParticipationStatus.CANCELLED)
                    .label("cancelled"),
                )
                .select_from(EventParticipation)
                .where(EventParticipation.user_id == user_id)
            )
            stats = result.first()

            upcoming = 0
            attended = 0
            cancelled = 0

            if stats:
                upcoming = int(getattr(stats, "upcoming", 0) or 0)
                attended = int(getattr(stats, "attended", 0) or 0)
                cancelled = int(getattr(stats, "cancelled", 0) or 0)

            total_completed = attended + cancelled
            attendance_rate = (
                (attended / total_completed * 100) if total_completed > 0 else 0.0
            )

            return {
                "upcoming_events": upcoming,
                "events_attended": attended,
                "events_cancelled": cancelled,
                "attendance_rate": round(attendance_rate, 1),
                "total_events": upcoming + attended + cancelled,
                "engagement_level": self._calculate_engagement_level(
                    upcoming + attended + cancelled
                ),
            }

        except Exception as e:
            return {
                "upcoming_events": 0,
                "events_attended": 0,
                "events_cancelled": 0,
                "attendance_rate": 0.0,
                "total_events": 0,
                "engagement_level": "unknown",
                "error": f"Could not fetch user statistics: {str(e)}",
            }

    def _calculate_engagement_level(self, total_events: int) -> str:
        if total_events == 0:
            return "new"
        elif total_events < 3:
            return "low"
        elif total_events < 10:
            return "moderate"
        elif total_events < 25:
            return "high"
        else:
            return "very_high"
