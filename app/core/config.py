from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="LV_", extra="ignore"
    )
    app_name: str = "LV – Wedding Planner"
    environment: str = "development"
    debug: bool = False
    secret_key: str = "change-me-before-production"
    database_url: str = "sqlite:///./data/lv_wedding_planner.db"
    uploads_dir: str = "uploads"
    backups_dir: str = "backups"
    session_https_only: bool = False
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    log_level: str = "INFO"
    max_upload_size_mb: int = 15

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
