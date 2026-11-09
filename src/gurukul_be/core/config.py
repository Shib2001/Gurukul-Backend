from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "gurukul-be"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://gurukul:dev-only-password@localhost:5432/gurukul"
    REDIS_URL: str = "redis://localhost:6379/0"
    FRONTEND_ORIGINS: str = "http://localhost:3000"
    AI_SERVICE_URL: str = "http://localhost:8001"
    AI_SERVICE_AUTH_KEY: str = "replace-me"
    SESSION_SECRET: str = "replace-me"
    OBJECT_STORAGE_BUCKET: str = "gurukul-local"
    OBJECT_STORAGE_ENDPOINT: str = "http://localhost:9000"
    OBJECT_STORAGE_ACCESS_KEY: str = "replace-me"
    OBJECT_STORAGE_SECRET_KEY: str = "replace-me"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
