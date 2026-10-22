from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STUDIO_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    database_url: str | None = None
    frontend_dir: Path | None = None
    max_upload_mb: int = 4096
    worker_poll_seconds: float = 1.0
    proxy_height: int = 960

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'studio.db'}"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.work_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
