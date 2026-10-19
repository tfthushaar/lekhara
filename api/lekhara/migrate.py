"""Database migrations.

python -m lekhara.migrate            upgrade to the latest schema
python -m lekhara.migrate revision "add bookings"   create a migration from model changes
"""

import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from lekhara.config import get_settings
from lekhara.db import make_engine


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "lekhara:migrations")
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Brings the schema up to date, then (on Postgres) puts the row-level security policies on
    every table that holds a firm's data, including tables the migrations just added."""
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)
        if connection.dialect.name == "postgresql":
            from lekhara import rls

            rls.install(connection)


def main(argv: list[str]) -> None:
    url = get_settings().database_url
    if len(argv) >= 2 and argv[0] == "revision":
        command.revision(alembic_config(url), message=argv[1], autogenerate=True)
        return
    upgrade(make_engine(url))
    print(f"Database at {url} is up to date.")


if __name__ == "__main__":
    main(sys.argv[1:])
