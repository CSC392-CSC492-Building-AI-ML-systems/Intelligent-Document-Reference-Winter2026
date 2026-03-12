"""Configuration for file-processor."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "file-processor"
    port: int = 8004
    debug: bool = False
    database_url: str = "postgresql://localhost/file_processor"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "FILE_PROCESSOR_"


settings = Settings()
