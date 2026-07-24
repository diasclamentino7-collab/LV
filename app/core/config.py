from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECRET_KEY = "change-me-before-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="LV_", extra="ignore"
    )
    app_name: str = "LV – Wedding Planner"
    environment: str = "development"
    debug: bool = False
    secret_key: str = DEFAULT_SECRET_KEY
    setup_token: str = ""
    database_url: str = "sqlite:///./data/lv_wedding_planner.db"
    uploads_dir: str = "uploads"
    backups_dir: str = "backups"
    session_https_only: bool = False
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    log_level: str = "INFO"
    max_upload_size_mb: int = 15

    @field_validator("database_url")
    @classmethod
    def use_installed_postgresql_driver(cls, value: str) -> str:
        """Accept provider URLs while explicitly selecting psycopg 3."""

        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def reject_unsafe_production_configuration(self) -> "Settings":
        """Fail before startup when production could expose sessions or lose data."""
        if self.environment.strip().casefold() not in {"production", "prod"}:
            return self

        problems: list[str] = []
        if self.secret_key.strip() == DEFAULT_SECRET_KEY or len(self.secret_key.strip()) < 32:
            problems.append("LV_SECRET_KEY must be a unique value with at least 32 characters")
        if not self.database_url.strip() or self.database_url.strip().casefold().startswith(
            "sqlite"
        ):
            problems.append("LV_DATABASE_URL must use a persistent non-SQLite database")
        if not self.session_https_only:
            problems.append("LV_SESSION_HTTPS_ONLY must be true")
        if len(self.setup_token.strip()) < 32:
            problems.append("LV_SETUP_TOKEN must contain at least 32 characters")
        if not self.allowed_host_list or "*" in self.allowed_host_list:
            problems.append("LV_ALLOWED_HOSTS must list trusted host names")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def static_path(self) -> Path:
        return PROJECT_ROOT / "app" / "static"

    @property
    def uploads_path(self) -> Path:
        return PROJECT_ROOT / self.uploads_dir

    @property
    def backups_path(self) -> Path:
        return PROJECT_ROOT / self.backups_dir

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
