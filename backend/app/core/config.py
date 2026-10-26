from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. Automation policy that must survive restarts lives in MongoDB."""

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    dry_run: bool = True
    automation_enabled: bool = False
    global_pause: bool = True
    min_match_score: int = Field(default=50, ge=0, le=100)
    discovery_interval_minutes: int = Field(default=60, ge=60, le=1440)
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "job_agent"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    cors_origins: str = "http://localhost:5173"
    app_secret_key: str = "dummy-change-me-to-a-long-random-value"
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = ""
    resume_storage_path: str = "./storage/resumes"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @field_validator("mongodb_url")
    @classmethod
    def mongodb_url_scheme(cls, value: str) -> str:
        if not value.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URL must start with mongodb:// or mongodb+srv://")
        return value

    @field_validator("redis_url", "celery_broker_url", "celery_result_backend")
    @classmethod
    def redis_url_scheme(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("Redis URLs must start with redis:// or rediss://")
        return value

    @field_validator("log_level")
    @classmethod
    def known_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {', '.join(sorted(allowed))}")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
