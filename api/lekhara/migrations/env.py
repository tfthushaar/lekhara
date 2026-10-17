"""Alembic environment. Run through `python -m lekhara.migrate` or the alembic CLI."""

from alembic import context

import lekhara.models  # noqa: F401  (registers every table on the metadata)
from lekhara.config import get_settings
from lekhara.db import Base, make_engine

config = context.config
target_metadata = Base.metadata

OPTIONS = {
    "target_metadata": target_metadata,
    "render_as_batch": True,  # SQLite needs batch mode to alter tables
    "user_module_prefix": "lekhara.db.",  # renders Money and Percent columns correctly
    "compare_type": True,
}


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_offline() -> None:
    context.configure(url=_url(), literal_binds=True, **OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, **OPTIONS)
        with context.begin_transaction():
            context.run_migrations()
        return
    with make_engine(_url()).connect() as connection:
        context.configure(connection=connection, **OPTIONS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
