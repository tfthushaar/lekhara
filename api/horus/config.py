from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HORUS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./horus.db"
    today: date | None = None
    """Fixes the date Horus treats as today. For demos and tests only."""

    def as_of(self) -> date:
        return self.today or date.today()


@lru_cache
def get_settings() -> Settings:
    return Settings()
