"""Database migrations.

python -m horus.migrate            upgrade to the latest schema
python -m horus.migrate revision "add bookings"   create a migration from model changes
"""

import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from horus.config import get_settings
from horus.db import make_engine


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "horus:migrations")
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)


def main(argv: list[str]) -> None:
    url = get_settings().database_url
    if len(argv) >= 2 and argv[0] == "revision":
        command.revision(alembic_config(url), message=argv[1], autogenerate=True)
        return
    upgrade(make_engine(url))
    print(f"Database at {url} is up to date.")


if __name__ == "__main__":
    main(sys.argv[1:])
