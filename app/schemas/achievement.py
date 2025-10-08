from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class AchievementCreate(BaseModel):
    user_id: int = Field(..., gt=0, description="User receiving the achievement")
    achievement_type: str = Field(..., min_length=1, max_length=100)
    points: int = Field(default=1, ge=1, description="Points value")
    reference_type: str | None = Field(None, max_length=50)
    reference_id: int | None = Field(None, gt=0)


class AchievementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    achievement_type: str
    points: int
    reference_type: str | None
    reference_id: int | None
    awarded_by_user_id: int
    created_at: datetime


class LeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    profile_image_url: str | None
    total_points: int
    achievement_count: int


class LeaderboardResponse(BaseModel):
    achievement_type: str
    total_points_awarded: int
    total_achievements: int
    unique_users: int
    leaderboard: list[LeaderboardEntry]


class UserAchievementStats(BaseModel):
    user_id: int
    total_points: int
    achievements_by_type: dict[str, int]
    total_achievements: int
