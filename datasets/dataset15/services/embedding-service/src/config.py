"""Configuration for embedding-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "embedding-service"
    port: int = 8011
    debug: bool = False
    database_url: str = "postgresql://localhost/embedding_service"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "EMBEDDING_SERVICE_"


settings = Settings()
