"""The API as Vercel runs it, for the public demo.

Vercel imports this module and serves `app`. Unless told otherwise it is the demo: the demo
accounts on the sign-in page, emails kept in the demo mailbox, sample files to bring in, the
shared demo accounts kept safe, and no background worker (a Vercel Function only runs while it
answers a request).

Vercel may run several copies of the API at once, so the demo keeps its data in one Postgres
database they all share: LEKHARA_DATABASE_URL, or the connection Neon sets up from the Vercel
Marketplace (DATABASE_URL and the like). Its files are kept in the same database. The first copy
to start brings the schema up to date and adds the demo firm if it isn't there; the others wait
for it. `reset` (from a nightly Vercel Cron job) puts the demo back as it began.

With no database given, each copy builds a demo of its own in /tmp, the one place a Vercel
Function may write. That is enough to look around, but a visitor whose requests reach different
copies sees different data.
"""

import os
import re
import tempfile
from pathlib import Path

HOME = Path(tempfile.gettempdir()) / "lekhara-demo"
LOCK = 7310
"""The Postgres advisory lock held while the demo is built or put back."""


def _shared_database() -> str | None:
    """Neon's connection from the Vercel Marketplace, for SQLAlchemy: the psycopg driver named,
    and the direct connection rather than the pooled one."""
    for name in (
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
        "DATABASE_URL",
        "POSTGRES_URL",
    ):
        url = os.environ.get(name)
        if url:
            return re.sub(r"^postgres(?:ql)?(?:\+\w+)?://", "postgresql+psycopg://", url)
    return None


os.environ.setdefault("LEKHARA_DEMO", "1")
os.environ.setdefault("LEKHARA_SHARED_DEMO", "1")
os.environ.setdefault("LEKHARA_WORKER", "0")
os.environ.setdefault("LEKHARA_AUTO_MIGRATE", "0")
os.environ.setdefault("LEKHARA_STORAGE_DIR", str(HOME / "files"))
_shared = _shared_database()
if _shared:
    os.environ.setdefault("LEKHARA_DATABASE_URL", _shared)
os.environ.setdefault("LEKHARA_DATABASE_URL", f"sqlite:///{(HOME / 'lekhara.db').as_posix()}")
if os.environ["LEKHARA_DATABASE_URL"].startswith("postgresql"):
    os.environ.setdefault("LEKHARA_STORAGE_URL", "database")
_host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
if _host:
    os.environ.setdefault("LEKHARA_WEB_URL", f"https://{_host}")

from sqlalchemy import select, text  # noqa: E402

from lekhara.app import create_app  # noqa: E402
from lekhara.config import get_settings  # noqa: E402
from lekhara.db import make_engine, make_sessionmaker  # noqa: E402
from lekhara.migrate import upgrade  # noqa: E402
from lekhara.models import Organization  # noqa: E402
from lekhara.seed import reset_and_seed, seed  # noqa: E402
from lekhara.storage import make_storage  # noqa: E402


def _build_in_tmp(url: str, *, again: bool = False) -> None:
    settings = get_settings()
    target = Path(url.removeprefix("sqlite:///"))
    if target.exists() and not again:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    # Built beside it and moved into place in one step, so a second process starting at the
    # same moment never opens a half-made database.
    partial = target.with_name(f"{target.name}.{os.getpid()}.partial")
    reset_and_seed(f"sqlite:///{partial.as_posix()}", settings.as_of(),
                   storage=make_storage(settings))  # fmt: skip
    if target.exists() and not again:
        partial.unlink(missing_ok=True)
    else:
        os.replace(partial, target)


def prepare() -> None:
    """Makes sure there is a demo to show."""
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///"):
        _build_in_tmp(url)
        return
    engine = make_engine(url)
    try:
        with engine.connect() as lock:
            lock.execute(text(f"SELECT pg_advisory_lock({LOCK})"))
            try:
                upgrade(engine)
                with make_sessionmaker(engine)() as session:
                    there = session.scalars(
                        select(Organization.id).where(Organization.id == "demo")
                    ).first()
                    if there is None:
                        seed(session, settings.as_of(), make_storage(settings))
            finally:
                lock.execute(text(f"SELECT pg_advisory_unlock({LOCK})"))
    finally:
        engine.dispose()


def reset() -> None:
    """Puts the demo back as it began: everything visitors added or changed goes."""
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///"):
        _build_in_tmp(url, again=True)
        return
    engine = make_engine(url)
    try:
        with engine.connect() as lock:
            lock.execute(text(f"SELECT pg_advisory_lock({LOCK})"))
            try:
                reset_and_seed(url, settings.as_of(), storage=make_storage(settings))
            finally:
                lock.execute(text(f"SELECT pg_advisory_unlock({LOCK})"))
    finally:
        engine.dispose()


prepare()
app = create_app()
app.state.reset_demo = reset
