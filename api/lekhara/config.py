from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEKHARA_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./lekhara.db"
    today: date | None = None
    """Fixes the date Lekhara treats as today. For demos and tests only."""
    auto_migrate: bool = True
    """Bring the database schema up to date when the API starts."""
    demo: bool = False
    """Show the demo accounts on the sign-in screen. Never set in production."""
    storage_dir: str = "./storage"
    """Where the document vault keeps files on local disk."""
    max_upload_mb: int = 20

    def as_of(self) -> date:
        return self.today or date.today()


@lru_cache
def get_settings() -> Settings:
    return Settings()
