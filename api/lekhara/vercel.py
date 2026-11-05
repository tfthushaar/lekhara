"""The API as Vercel runs it, for the public demo.

Vercel imports this module and serves `app`. Unless told otherwise it is the demo: the demo
accounts on the sign-in page, emails kept in the demo mailbox, sample files to bring in, and no
background worker (a Vercel Function only runs while it answers a request).

With no LEKHARA_DATABASE_URL, the database and files live in /tmp, the one place a Vercel
Function may write. Each new instance fills them with the demo firm when it starts, which takes
a second or two, so the demo puts itself back together whenever Vercel starts a fresh instance.
With LEKHARA_DATABASE_URL set (a Postgres database), the schema is brought up to date and the
demo firm is added only when the database has none yet, so changes last until it is reset.
"""

import os
import tempfile
from pathlib import Path

HOME = Path(tempfile.gettempdir()) / "lekhara-demo"

os.environ.setdefault("LEKHARA_DEMO", "1")
os.environ.setdefault("LEKHARA_SHARED_DEMO", "1")
os.environ.setdefault("LEKHARA_WORKER", "0")
os.environ.setdefault("LEKHARA_AUTO_MIGRATE", "0")
os.environ.setdefault("LEKHARA_STORAGE_DIR", str(HOME / "files"))
os.environ.setdefault("LEKHARA_DATABASE_URL", f"sqlite:///{(HOME / 'lekhara.db').as_posix()}")
_host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
if _host:
    os.environ.setdefault("LEKHARA_WEB_URL", f"https://{_host}")

from sqlalchemy import select  # noqa: E402

from lekhara.app import create_app  # noqa: E402
from lekhara.config import get_settings  # noqa: E402
from lekhara.db import make_engine, make_sessionmaker  # noqa: E402
from lekhara.migrate import upgrade  # noqa: E402
from lekhara.models import Organization  # noqa: E402
from lekhara.seed import reset_and_seed, seed  # noqa: E402
from lekhara.storage import make_storage  # noqa: E402


def prepare() -> None:
    """Makes sure there is a demo to show: a fresh one in /tmp, or the demo firm added to an
    empty Postgres database."""
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///"):
        target = Path(url.removeprefix("sqlite:///"))
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        # Built beside it and moved into place in one step, so a second process starting at
        # the same moment never opens a half-made database.
        partial = target.with_name(f"{target.name}.{os.getpid()}.partial")
        reset_and_seed(f"sqlite:///{partial.as_posix()}", settings.as_of(),
                       storage=make_storage(settings))  # fmt: skip
        if target.exists():
            partial.unlink(missing_ok=True)
        else:
            os.replace(partial, target)
        return
    engine = make_engine(url)
    upgrade(engine)
    with make_sessionmaker(engine)() as session:
        if session.scalars(select(Organization.id).where(Organization.id == "demo")).first():
            return
        seed(session, settings.as_of(), make_storage(settings))


prepare()
app = create_app()
