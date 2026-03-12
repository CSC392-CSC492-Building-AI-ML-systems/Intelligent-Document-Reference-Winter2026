"""Configuration for auth-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "auth-service"
    port: int = 8043
    debug: bool = False
    database_url: str = "postgresql://localhost/auth_service"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "AUTH_SERVICE_"


settings = Settings()
