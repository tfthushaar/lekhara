from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from lekhara.db import Base, make_engine
from lekhara.migrate import upgrade


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


def test_upgrade_keeps_existing_data(tmp_path) -> None:
    """Each new migration must apply to a database that already holds projects."""
    from alembic import command
    from alembic.script import ScriptDirectory

    from lekhara.migrate import alembic_config

    engine = make_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    cfg = alembic_config()
    revisions = [s.revision for s in ScriptDirectory.from_config(cfg).walk_revisions()]
    previous = revisions[1] if len(revisions) > 1 else revisions[0]
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, previous)
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO organizations (id, name) VALUES ('o', 'Org')")
        connection.exec_driver_sql(
            "INSERT INTO projects (id, organization_id, name, locality, city, krera_registration,"
            " registered_on, spv_name, gst_regime, land_structure, cess_paid) VALUES ('p', 'o',"
            " 'P', 'L', 'C', 'R', '2025-01-01', 'S', 'residential_5pc', 'own', 0)"
        )
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM projects").scalar() == 1
