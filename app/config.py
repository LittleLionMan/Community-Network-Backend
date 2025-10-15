from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import os


def _get_secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if not key:
        raise ValueError("SECRET_KEY environment variable is required")
    return key


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")
    return url


class Settings(BaseSettings):
    APP_NAME: str = "Community Platform API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = Field(
        default_factory=_get_secret_key, description="Secret key for JWT tokens"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DATABASE_URL: str = Field(
        default_factory=_get_database_url, description="Database connection URL"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    UPLOAD_DIR: str = "/app/uploads"
    MAX_FILE_SIZE: int = 5242880
    ALLOWED_IMAGE_EXTENSIONS: str = ".jpg,.jpeg,.png,.gif,.webp"

    CORS_ORIGINS: str = Field(
        default="https://plaetzchen.com,https://www.plaetzchen.com,http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000",
        description="Comma-separated list of allowed origins",
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = Field(default=["*"])
    CORS_ALLOW_HEADERS: list[str] = Field(default=["*"])

    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    GEOCODING_API_KEY: str | None = None

    CONTENT_MODERATION_ENABLED: bool = True
    MODERATION_THRESHOLD: float = 0.7
    MODERATION_AUTO_FLAG_THRESHOLD: float = 0.9

    CLAMAV_ENABLED: bool = False
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310

    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str | None = None
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
        env_file=".env", case_sensitive=True, env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        if not v:
            raise ValueError("CORS_ORIGINS cannot be empty")

        origins = [origin.strip() for origin in v.split(",")]
        for origin in origins:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"Invalid CORS origin format: {origin}. Must start with http:// or https://"
                )

        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @property
    def allowed_image_types(self) -> list[str]:
        return [ext.strip() for ext in self.ALLOWED_IMAGE_EXTENSIONS.split(",")]

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    @property
    def backend_cors_origins(self) -> list[str]:
        return self.cors_origins_list


settings = Settings()  # type: ignore[call-arg]


def _validate_settings() -> None:
    if not os.getenv("SKIP_CONFIG_VALIDATION"):
        from .core.config_validator import EnvironmentValidator

        EnvironmentValidator.validate_or_exit()


_validate_settings()
