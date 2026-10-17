from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from horus.db import Base, make_engine
from horus.migrate import upgrade


def test_migrations_build_the_same_schema_as_the_models(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    upgrade(engine)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)
    assert differences == [], differences


def test_upgrade_is_repeatable(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'twice.db'}")
    upgrade(engine)
    upgrade(engine)
