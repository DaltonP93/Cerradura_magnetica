"""Production hardening: no insecure defaults, no demo seed in production.

Phase 1 item 6. These construct Settings directly (bypassing the cached
get_settings) so each scenario is isolated from the process environment.
"""
import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, DEFAULT_SUPERUSER_PASSWORD, Settings
from app.seed import seed

STRONG_SECRET = "k" * 40
STRONG_PASSWORD = "a-unique-strong-password"


def _prod(**overrides) -> dict:
    base = {
        "environment": "production",
        "secret_key": STRONG_SECRET,
        "first_superuser_password": STRONG_PASSWORD,
        "debug": False,
    }
    base.update(overrides)
    return base


def test_development_defaults_are_allowed():
    cfg = Settings(environment="development", secret_key=DEFAULT_SECRET_KEY)
    assert cfg.is_production is False
    # Defaults are flagged as production problems even though dev tolerates them.
    assert cfg.production_issues()


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(**_prod(secret_key=DEFAULT_SECRET_KEY))


def test_production_rejects_short_secret_key():
    with pytest.raises(ValidationError):
        Settings(**_prod(secret_key="too-short"))


def test_production_rejects_default_superuser_password():
    with pytest.raises(ValidationError):
        Settings(**_prod(first_superuser_password=DEFAULT_SUPERUSER_PASSWORD))


def test_production_rejects_debug_true():
    with pytest.raises(ValidationError):
        Settings(**_prod(debug=True))


def test_production_accepts_strong_config():
    cfg = Settings(**_prod())
    assert cfg.is_production is True
    assert cfg.production_issues() == []


def test_seed_refuses_to_run_in_production():
    cfg = Settings(**_prod())
    with pytest.raises(SystemExit):
        seed(cfg)
