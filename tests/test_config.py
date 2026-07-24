import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings

SAFE_PRODUCTION_VALUES = {
    "environment": "production",
    "secret_key": "s" * 64,
    "setup_token": "t" * 64,
    "database_url": "postgresql+psycopg://user:password@database.example/app",
    "session_https_only": True,
    "allowed_hosts": "*.onrender.com",
}


def production_settings(**overrides) -> Settings:
    values = {**SAFE_PRODUCTION_VALUES, **overrides}
    return Settings(_env_file=None, **values)


def test_development_defaults_remain_available() -> None:
    settings = Settings(_env_file=None, environment="development")

    assert settings.database_url.startswith("sqlite")
    assert settings.secret_key == DEFAULT_SECRET_KEY
    assert settings.session_https_only is False
    assert settings.setup_token == ""


def test_safe_production_configuration_is_accepted() -> None:
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.database_url.startswith("postgresql")
    assert settings.session_https_only is True


@pytest.mark.parametrize("scheme", ["postgresql://", "postgres://"])
def test_provider_database_urls_use_psycopg_three(scheme: str) -> None:
    settings = production_settings(database_url=f"{scheme}user:password@database.example/app")

    assert settings.database_url.startswith("postgresql+psycopg://")


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"secret_key": DEFAULT_SECRET_KEY}, "LV_SECRET_KEY"),
        ({"secret_key": f"  {DEFAULT_SECRET_KEY}  "}, "LV_SECRET_KEY"),
        ({"secret_key": "short"}, "LV_SECRET_KEY"),
        ({"secret_key": " " * 64}, "LV_SECRET_KEY"),
        ({"database_url": "sqlite:///./production.db"}, "LV_DATABASE_URL"),
        ({"session_https_only": False}, "LV_SESSION_HTTPS_ONLY"),
        ({"setup_token": ""}, "LV_SETUP_TOKEN"),
        ({"setup_token": " " * 64}, "LV_SETUP_TOKEN"),
        ({"allowed_hosts": "*"}, "LV_ALLOWED_HOSTS"),
    ],
)
def test_unsafe_production_configuration_is_rejected(
    overrides: dict[str, object],
    expected_error: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_error):
        production_settings(**overrides)
