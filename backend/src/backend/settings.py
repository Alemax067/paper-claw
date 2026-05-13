from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_DATABASE_URL = "postgresql+psycopg://paper_claw:paper_claw@localhost:5432/paper_claw"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PAPER_CLAW_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    data_dir: Path = Field(default_factory=lambda: DATA_DIR)
    storage_root: Path | None = None
    arxiv_min_interval_seconds: float = 1.0
    arxiv_max_retries: int = 3
    arxiv_backoff_base_seconds: float = 1.0
    arxiv_backoff_max_seconds: float = 30.0

    def model_post_init(self, __context: object) -> None:
        self.data_dir = self.data_dir.expanduser().resolve()
        if self.storage_root is None:
            self.storage_root = self.data_dir / "files"
        else:
            self.storage_root = self.storage_root.expanduser().resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
