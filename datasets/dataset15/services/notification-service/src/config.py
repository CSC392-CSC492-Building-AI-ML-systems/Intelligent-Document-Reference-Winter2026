"""Configuration for notification-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "notification-service"
    port: int = 8034
    debug: bool = False
    database_url: str = "postgresql://localhost/notification_service"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "NOTIFICATION_SERVICE_"


settings = Settings()
