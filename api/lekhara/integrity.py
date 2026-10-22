"""A nightly check that every stored file is still there and unchanged.

Files are stored under the SHA-256 of their contents, so a file can be checked against its own
name: one missing, or whose contents no longer match, means the storage lost or changed it
(a failing disk, a bad copy, or someone tampering). Every file a record refers to is read and
hashed; the result is kept, shown in the admin console, and logged as an error when anything
is wrong. Run it by hand with

    python -m lekhara.integrity
"""

import hashlib
import json
import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import jobs
from lekhara.models import (
    BankStatement,
    Connector,
    Document,
    GstImport,
    InboundItem,
    InboundMessage,
    IntegrityCheck,
    TallyImport,
    utcnow,
)
from lekhara.storage import Storage

log = logging.getLogger("lekhara.integrity")

FILE_COLUMNS = (
    (Document, "storage_key", "document"),
    (TallyImport, "storage_key", "Tally import"),
    (BankStatement, "storage_key", "bank statement"),
    (GstImport, "storage_key", "GST return"),
    (InboundMessage, "storage_key", "email received"),
    (InboundItem, "storage_key", "emailed file"),
    (Connector, "masters_key", "connector's Tally masters"),
)
"""Every column that names a stored file. A new one must be added here."""


def check_files(session: Session, storage: Storage) -> IntegrityCheck:
    checked, problems = set(), []
    for model, column, what in FILE_COLUMNS:
        for row_id, key in session.execute(select(model.id, getattr(model, column))):
            if not key or key in checked:
                continue
            checked.add(key)
            try:
                data = storage.get(key)
            except (FileNotFoundError, ValueError):
                problems.append({"what": what, "id": row_id, "key": key, "problem": "missing"})
                continue
            if hashlib.sha256(data).hexdigest() != key:
                problems.append({"what": what, "id": row_id, "key": key, "problem": "altered"})
    result = IntegrityCheck(
        at=utcnow(),
        checked=len(checked),
        missing=sum(p["problem"] == "missing" for p in problems),
        altered=sum(p["problem"] == "altered" for p in problems),
        problems=json.dumps(problems[:200]),
    )
    session.add(result)
    session.commit()
    if problems:
        log.error("File check: %s missing, %s altered.", result.missing, result.altered)
    return result


def latest(session: Session) -> IntegrityCheck | None:
    return session.scalars(select(IntegrityCheck).order_by(IntegrityCheck.at.desc())).first()


@jobs.handler("files.check")
def _nightly(ctx: jobs.Context, payload: dict) -> None:
    check_files(ctx.session, ctx.storage)


jobs.every("files.check", 24 * 3600)


def main() -> int:
    from lekhara.config import get_settings
    from lekhara.db import make_engine, make_sessionmaker
    from lekhara.storage import make_storage

    settings = get_settings()
    with make_sessionmaker(make_engine(settings.database_url))() as session:
        result = check_files(session, make_storage(settings))
    print(f"{result.checked} files checked: {result.missing} missing, {result.altered} altered.")
    for problem in json.loads(result.problems):
        print(f"  {problem['problem']}: {problem['what']} {problem['id']} ({problem['key']})")
    return 1 if result.missing or result.altered else 0


if __name__ == "__main__":
    sys.exit(main())
