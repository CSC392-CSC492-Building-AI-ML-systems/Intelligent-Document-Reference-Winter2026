"""Configuration for analytics-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "analytics-service"
    port: int = 8026
    debug: bool = False
    database_url: str = "postgresql://localhost/analytics_service"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "ANALYTICS_SERVICE_"


settings = Settings()
