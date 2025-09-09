from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, List
import os
from .core.config_validator import EnvironmentValidator

class Settings(BaseSettings):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not os.getenv('SKIP_CONFIG_VALIDATION'):
            EnvironmentValidator.validate_or_exit()

    APP_NAME: str = "Community Platform API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    SECRET_KEY: str  # ✅ Will be validated
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    DATABASE_URL: str  # ✅ Will be validated
    REDIS_URL: str = "redis://localhost:6379/0"

    UPLOAD_DIR: str = "/app/uploads"
    MAX_FILE_SIZE: int = 5242880  # 5MB
    ALLOWED_IMAGE_EXTENSIONS: str = ".jpg,.jpeg,.png,.gif,.webp"

    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"]
    )

    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: str = "noreply@community-platform.local"
    EMAIL_ENABLED: bool = False
    EMAIL_VERIFICATION_REQUIRED: bool = True

    GEOCODING_API_KEY: Optional[str] = None

    CONTENT_MODERATION_ENABLED: bool = True
    MODERATION_THRESHOLD: float = 0.7
    MODERATION_AUTO_FLAG_THRESHOLD: float = 0.9

    CLAMAV_ENABLED: bool = False
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310

    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None
    METRICS_ENABLED: bool = True

    EVENT_REGISTRATION_DEADLINE_HOURS: int = 24
    EVENT_AUTO_ATTENDANCE_ENABLED: bool = True
    EVENT_AUTO_ATTENDANCE_DELAY_HOURS: int = 1

    SERVICE_MATCHING_ENABLED: bool = True
    SERVICE_MATCHING_MAX_KEYWORDS: int = 5

    POLL_DEFAULT_DURATION_HOURS: int = 48
    POLL_ADMIN_DURATION_HOURS: int = 168
    POLL_MAX_OPTIONS: int = 10

    USER_INACTIVE_THRESHOLD_DAYS: int = 30
    MESSAGE_CLEANUP_DAYS: int = 365

    DB_ECHO: bool = False
    DOCS_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == 'production'

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == 'development'

    @property
    def allowed_image_types(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_IMAGE_EXTENSIONS.split(',')]

    @property
    def cors_origins(self) -> List[str]:
        if self.is_development:
            return [
                "http://localhost:3000",
                "http://localhost:8080",
                "http://127.0.0.1:3000"
            ]
        else:
            cors_env = os.getenv("CORS_ORIGINS", "")
            if cors_env:
                return [origin.strip() for origin in cors_env.split(",") if origin.strip()]
            return self.BACKEND_CORS_ORIGINS

settings = Settings()
