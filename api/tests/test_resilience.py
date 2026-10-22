"""Changing the secret key without losing secrets, an access log that shows tampering, limits
shared by every server, and encrypted backups that refuse to restore when altered."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from lekhara import backup, legal, secretbox
from lekhara.app import create_app
from lekhara.config import Settings
from lekhara.db import Base, make_engine, make_sessionmaker
from lekhara.models import AccessEvent, StatementPassword
from lekhara.seed import DEMO_PASSWORD, seed
from lekhara.storage import LocalStorage


def test_the_secret_key_can_change_without_losing_secrets(engine) -> None:
    old = Settings(database_url="sqlite://", secret_key="the-old-key-1234567890")
    new = Settings(database_url="sqlite://", secret_key="the-new-key-0987654321")
    both = Settings(
        database_url="sqlite://",
        secret_key="the-new-key-0987654321",
        old_secret_keys="the-old-key-1234567890",
    )
    with make_sessionmaker(engine)() as session:
        org_id = session.execute(text("select id from organizations limit 1")).scalar()
        session.add(
            StatementPassword(
                organization_id=org_id, label="HDFC", sealed=secretbox.seal(old, "DOB01011980")
            )
        )
        session.commit()
        row = session.scalars(select(StatementPassword)).first()
        assert secretbox.unseal(new, row.sealed) is None  # the new key alone cannot open it
        assert secretbox.unseal(both, row.sealed) == "DOB01011980"
        done, failed = secretbox.reseal_all(session, both)
        assert done >= 1 and failed == 0
        row = session.scalars(select(StatementPassword)).first()
        assert secretbox.unseal(new, row.sealed) == "DOB01011980"
        assert secretbox.unseal(old, row.sealed) is None


def test_the_access_log_shows_any_change(app) -> None:
    for _ in range(3):
        r = TestClient(app).post(
            "/auth/login", json={"email": "promoter@demo.lekhara", "password": DEMO_PASSWORD}
        )
        assert r.status_code == 200
    with app.state.session_factory() as session:
        result = legal.verify_log(session)
        assert result["intact"] and result["checked"] >= 3

        # Someone with database access rewrites who signed in.
        second = session.scalars(select(AccessEvent).order_by(AccessEvent.seq).offset(1)).first()
        second.who = "someone-else@example.com"
        session.commit()
        tampered = second.id
        broken = legal.verify_log(session)
        assert broken["intact"] is False and broken["broken_at"] == second.seq
        session.rollback()

    with app.state.session_factory() as session:
        # Taking out the newest event is caught too.
        session.get(AccessEvent, tampered).who = "promoter@demo.lekhara"
        session.commit()
        assert legal.verify_log(session)["intact"]
        newest = session.scalars(select(AccessEvent).order_by(AccessEvent.seq.desc())).first()
        session.delete(newest)
        session.commit()
        assert legal.verify_log(session)["intact"] is False


def test_limits_are_shared_by_every_server(engine, tmp_path) -> None:
    def server():
        settings = Settings(
            database_url="sqlite://",
            today=date(2026, 10, 17),
            auto_migrate=False,
            storage_dir=str(tmp_path / "files"),
            failed_logins_per_address=3,
        )
        return TestClient(create_app(settings, engine=engine))

    first, second = server(), server()
    for email in ("a@x.in", "b@x.in"):
        assert first.post("/auth/login", json={"email": email, "password": "x"}).status_code == 401
    assert second.post("/auth/login", json={"email": "c@x.in", "password": "x"}).status_code == 401
    # Three failures across two servers: the fourth attempt, on either, is refused.
    blocked = first.post("/auth/login", json={"email": "d@x.in", "password": "x"})
    assert blocked.status_code == 429


@pytest.fixture
def live(tmp_path):
    """A database on disk with the demo data and its files, as a real server has."""
    db = tmp_path / "lekhara.db"
    files = tmp_path / "files"
    engine = make_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as session:
        seed(session, date(2026, 10, 17), LocalStorage(files))
    engine.dispose()
    return Settings(
        database_url=f"sqlite:///{db}",
        storage_dir=str(files),
        backup_key="a long backup passphrase",
    )


def test_a_backup_checks_out_and_restores(live, tmp_path) -> None:
    made = backup.create(live, tmp_path / "backups")
    result = backup.check(live, made)
    assert result["problems"] == [] and result["firms"] >= 1 and result["files"] > 0

    restored = backup.restore(live, made, tmp_path / "restored")
    assert restored["problems"] == []
    assert (tmp_path / "restored" / "database" / "lekhara.sqlite").exists()

    with pytest.raises(backup.BackupError, match="new, empty folder"):
        backup.restore(live, made, tmp_path / "restored")


def test_an_altered_backup_is_refused(live, tmp_path) -> None:
    made = backup.create(live, tmp_path / "backups")
    data = bytearray(made.read_bytes())

    altered = tmp_path / "altered.lkb"
    data[len(data) // 2] ^= 0xFF
    altered.write_bytes(bytes(data))
    with pytest.raises(backup.BackupError, match="does not open"):
        backup.check(live, altered)

    short = tmp_path / "short.lkb"
    short.write_bytes(made.read_bytes()[: len(data) - 100])
    with pytest.raises(backup.BackupError):
        backup.check(live, short)

    wrong = Settings(**{**live.model_dump(), "backup_key": "not the right passphrase"})
    with pytest.raises(backup.BackupError, match="key is wrong"):
        backup.check(wrong, made)

    with pytest.raises(backup.BackupError, match="LEKHARA_BACKUP_KEY"):
        backup.create(Settings(**{**live.model_dump(), "backup_key": None}), tmp_path)


def test_events_written_at_once_keep_one_chain(tmp_path) -> None:
    """Requests arriving together (a page asks for several things at once) queue on the chain's
    end rather than forking it."""
    import threading

    engine = make_engine(f"sqlite:///{tmp_path / 'log.db'}")
    Base.metadata.create_all(engine)
    make = make_sessionmaker(engine)
    start = threading.Barrier(20)

    def write(n: int) -> None:
        with make() as session:
            start.wait()
            legal.record(session, "support_view", detail=f"/page/{n}")

    threads = [threading.Thread(target=write, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with make() as session:
        legal.seal_log(session)
        seqs = [e.seq for e in session.scalars(select(AccessEvent).order_by(AccessEvent.seq))]
        assert seqs == list(range(1, 21))
        assert legal.verify_log(session) == {"intact": True, "checked": 20, "broken_at": None}
