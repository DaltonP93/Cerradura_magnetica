"""Application configuration loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ACP_", extra="ignore")

    app_name: str = "Access Control Platform"
    environment: str = "development"
    debug: bool = False

    # Security
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    # Database. SQLite by default for local development; Postgres in production.
    database_url: str = "sqlite:///./access_control.db"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Hardware gateway: "simulated" runs an in-process L04 simulator,
    # "tcp" talks to real boards on the network.
    gateway_mode: str = "simulated"
    gateway_poll_interval_seconds: int = 30

    # Initial super admin (created by the seed command if no users exist)
    first_superuser_email: str = "admin@example.com"
    first_superuser_password: str = "admin1234"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
