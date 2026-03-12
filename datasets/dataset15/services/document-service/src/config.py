"""Configuration for document-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "document-service"
    port: int = 8075
    debug: bool = False
    database_url: str = "postgresql://localhost/document_service"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "DOCUMENT_SERVICE_"


settings = Settings()
