"""Application configuration loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Insecure defaults that are fine for local development but must never reach a
# production deployment.
DEFAULT_SECRET_KEY = "change-me-in-production"
DEFAULT_SUPERUSER_PASSWORD = "admin1234"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ACP_", extra="ignore")

    app_name: str = "Access Control Platform"
    environment: str = "development"
    debug: bool = False

    # Security
    secret_key: str = DEFAULT_SECRET_KEY
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

    # How often a live WebSocket re-checks that its session is still valid, so
    # revocations performed in another worker/process are picked up even without
    # an immediate cross-process signal.
    ws_revalidate_seconds: float = 15.0

    # Initial super admin (created by the seed command if no users exist)
    first_superuser_email: str = "admin@example.com"
    first_superuser_password: str = DEFAULT_SUPERUSER_PASSWORD

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def production_issues(self) -> list[str]:
        """List insecure-default problems that must be fixed before production."""
        issues: list[str] = []
        if self.secret_key == DEFAULT_SECRET_KEY or len(self.secret_key) < MIN_SECRET_KEY_LENGTH:
            issues.append(
                f"ACP_SECRET_KEY must be a unique value of at least {MIN_SECRET_KEY_LENGTH} characters"
            )
        if self.first_superuser_password == DEFAULT_SUPERUSER_PASSWORD:
            issues.append("ACP_FIRST_SUPERUSER_PASSWORD must be changed from its default")
        if self.debug:
            issues.append("ACP_DEBUG must be false in production")
        return issues

    @model_validator(mode="after")
    def _fail_fast_on_unsafe_production(self) -> "Settings":
        """Refuse to start a production deployment that still uses demo defaults."""
        if self.is_production:
            issues = self.production_issues()
            if issues:
                raise ValueError(
                    "Insecure production configuration — " + "; ".join(issues)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
