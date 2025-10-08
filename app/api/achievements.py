from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Annotated

from app.database import get_db
from app.models.achievement import UserAchievement
from app.models.user import User
from app.models.event import Event
from app.schemas.achievement import (
    AchievementCreate,
    AchievementRead,
    LeaderboardEntry,
    LeaderboardResponse,
    UserAchievementStats,
)
from app.core.dependencies import get_current_user
from app.core.logging import SecurityLogger

router = APIRouter()


async def _check_award_permission(
    achievement_type: str,
    reference_type: str | None,
    reference_id: int | None,
    current_user: User,
    db: AsyncSession,
) -> bool:
    if achievement_type == "bug_bounty":
        return current_user.is_admin

    if achievement_type.startswith("event_"):
        if current_user.is_admin:
            return True
        if reference_type == "event" and reference_id:
            result = await db.execute(select(Event).where(Event.id == reference_id))
            event = result.scalar_one_or_none()
            if event:
                return event.creator_id == current_user.id
            return False

    return current_user.is_admin


@router.post(
    "/achievements", response_model=AchievementRead, status_code=status.HTTP_201_CREATED
)
async def create_achievement(
    request: Request,
    achievement_data: AchievementCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    has_permission = await _check_award_permission(
        achievement_data.achievement_type,
        achievement_data.reference_type,
        achievement_data.reference_id,
        current_user,
        db,
    )

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No permission"
        )

    result = await db.execute(select(User).where(User.id == achievement_data.user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if achievement_data.reference_type and achievement_data.reference_id:
        existing = await db.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == achievement_data.user_id,
                UserAchievement.achievement_type == achievement_data.achievement_type,
                UserAchievement.reference_type == achievement_data.reference_type,
                UserAchievement.reference_id == achievement_data.reference_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Already awarded"
            )

    achievement = UserAchievement(
        user_id=achievement_data.user_id,
        achievement_type=achievement_data.achievement_type,
        points=achievement_data.points,
        reference_type=achievement_data.reference_type,
        reference_id=achievement_data.reference_id,
        awarded_by_user_id=current_user.id,
    )

    db.add(achievement)
    await db.commit()
    await db.refresh(achievement)

    SecurityLogger.log_admin_action(
        request,
        admin_user_id=current_user.id,
        action="award_achievement",
        details={
            "achievement_id": achievement.id,
            "target_user_id": achievement_data.user_id,
        },
    )

    return AchievementRead.model_validate(achievement)


@router.delete("/achievements/{achievement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_achievement(
    request: Request,
    achievement_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(UserAchievement).where(UserAchievement.id == achievement_id)
    )
    achievement = result.scalar_one_or_none()

    if not achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if not current_user.is_admin and achievement.awarded_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized"
        )

    _ = await db.execute(
        delete(UserAchievement).where(UserAchievement.id == achievement_id)
    )
    await db.commit()

    SecurityLogger.log_admin_action(
        request, admin_user_id=current_user.id, action="delete_achievement"
    )


@router.get("/achievements/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    achievement_type: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    result = await db.execute(
        select(
            User.id,
            User.display_name,
            User.profile_image_url,
            func.sum(UserAchievement.points).label("total_points"),
            func.count(UserAchievement.id).label("achievement_count"),
        )
        .join(UserAchievement, User.id == UserAchievement.user_id)
        .where(UserAchievement.achievement_type == achievement_type)
        .group_by(User.id, User.display_name, User.profile_image_url)
        .order_by(func.sum(UserAchievement.points).desc())
        .limit(limit)
    )

    leaderboard = [
        LeaderboardEntry(
            user_id=r[0],
            display_name=r[1],
            profile_image_url=r[2],
            total_points=r[3] or 0,
            achievement_count=r[4] or 0,
        )
        for r in result.all()
    ]

    total_points = await db.execute(
        select(func.sum(UserAchievement.points)).where(
            UserAchievement.achievement_type == achievement_type
        )
    )
    total_achievements = await db.execute(
        select(func.count(UserAchievement.id)).where(
            UserAchievement.achievement_type == achievement_type
        )
    )
    unique_users = await db.execute(
        select(func.count(func.distinct(UserAchievement.user_id))).where(
            UserAchievement.achievement_type == achievement_type
        )
    )

    return LeaderboardResponse(
        achievement_type=achievement_type,
        total_points_awarded=total_points.scalar() or 0,
        total_achievements=total_achievements.scalar() or 0,
        unique_users=unique_users.scalar() or 0,
        leaderboard=leaderboard,
    )


@router.get("/achievements/my-stats", response_model=UserAchievementStats)
async def get_my_achievement_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    total_points_result = await db.execute(
        select(func.sum(UserAchievement.points)).where(
            UserAchievement.user_id == current_user.id
        )
    )

    achievements_by_type_result = await db.execute(
        select(UserAchievement.achievement_type, func.count(UserAchievement.id))
        .where(UserAchievement.user_id == current_user.id)
        .group_by(UserAchievement.achievement_type)
    )

    achievements_by_type = {
        ach_type: count for ach_type, count in achievements_by_type_result.all()
    }

    return UserAchievementStats(
        user_id=current_user.id,
        total_points=total_points_result.scalar() or 0,
        achievements_by_type=achievements_by_type,
        total_achievements=sum(achievements_by_type.values()),
    )


@router.get("/achievements/user/{user_id}", response_model=list[AchievementRead])
async def get_user_achievements(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    achievement_type: Annotated[str | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    query = select(UserAchievement).where(UserAchievement.user_id == user_id)

    if achievement_type:
        query = query.where(UserAchievement.achievement_type == achievement_type)

    query = query.order_by(UserAchievement.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    return [AchievementRead.model_validate(a) for a in result.scalars().all()]
