"""Configuration for api-gateway."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "api-gateway"
    port: int = 8053
    debug: bool = False
    database_url: str = "postgresql://localhost/api_gateway"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    class Config:
        env_prefix = "API_GATEWAY_"


settings = Settings()
