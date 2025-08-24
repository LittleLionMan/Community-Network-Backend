from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import os

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Community Platform API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # External APIs
    GEOCODING_API_KEY: Optional[str] = None

    # Anti-Toxicity
    CONTENT_MODERATION_ENABLED: bool = True
    MODERATION_THRESHOLD: float = 0.7
    MODERATION_AUTO_FLAG_THRESHOLD: float = 0.9
    MODERATION_REVIEW_THRESHOLD: float = 0.3

    # Event Business Rules
    EVENT_REGISTRATION_DEADLINE_HOURS: int = 24
    EVENT_AUTO_ATTENDANCE_ENABLED: bool = True
    EVENT_AUTO_ATTENDANCE_DELAY_HOURS: int = 1

    # Service Matching Settings
    SERVICE_MATCHING_ENABLED: bool = True
    SERVICE_MATCHING_MAX_KEYWORDS: int = 5
    SERVICE_RECOMMENDATIONS_LIMIT: int = 10

    # Voting System Settings
    POLL_DEFAULT_DURATION_HOURS: int = 48
    POLL_ADMIN_DURATION_HOURS: int = 168  # 1 week
    POLL_MAX_OPTIONS: int = 10
    POLL_MIN_OPTIONS: int = 2

    # User Engagement Settings
    USER_INACTIVE_THRESHOLD_DAYS: int = 30
    USER_HIGH_ENGAGEMENT_THRESHOLD: int = 15

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings() #type: ignore
