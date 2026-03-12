"""Configuration for search-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "search-service"
    port: int = 8033
    debug: bool = False
    database_url: str = "postgresql://localhost/search_service"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "SEARCH_SERVICE_"


settings = Settings()
