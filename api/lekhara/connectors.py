"""Connectors: programs on the builder's own computers that feed a project by themselves.

The Lekhara Connector for Tally runs on the computer with Tally. A team member asks for a short
code on the project's Import page and types it into the connector, which then gets its own key:
the key lets it send data to that one project and nothing else, and unlinking the computer
withdraws it. The connector reads TallyPrime's own exports over its local XML interface (masters,
and the Day Book for recent days and, nightly, the whole year) and sends them here; each sync
goes through the Tally import, matched on Tally's own voucher identities, so a sync that brings
nothing new adds nothing.

A sync is applied by itself. What needs a choice (a buyer's ledger with no unit, an expense
ledger with no cost line) waits, shows in the review queue, and comes in on the next sync once
the choice is made: choices belong to the project, not to one import.
"""

import hashlib
import re
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import services
from lekhara.config import Settings
from lekhara.models import Connector, Organization, Project, utcnow
from lekhara.services import ServiceError
from lekhara.storage import Storage
from lekhara.tally import service as tally
from lekhara.tally.reader import decode

CODE_MINUTES = 30
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INTERVAL_SECONDS = 300
RECENT_DAYS = 7
FULL_SYNC_HOURS = 24


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _normal_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def new_code(session: Session, project: Project, *, user_id: str | None) -> tuple[Connector, str]:
    """A pending connector and the one-time code that links a computer to it."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    connector = Connector(
        organization_id=project.organization_id,
        project_id=project.id,
        kind="tally",
        status="pending",
        code_hash=_hash(raw),
        code_expires_at=utcnow() + timedelta(minutes=CODE_MINUTES),
        created_by_user_id=user_id,
    )
    session.add(connector)
    session.commit()
    return connector, f"{raw[:4]}-{raw[4:]}"


def link(session: Session, code: str, name: str | None) -> tuple[Connector, str]:
    """Exchange a code typed into the connector for the connector's own key."""
    normal = _normal_code(code)
    connector = session.scalars(
        select(Connector).where(Connector.code_hash == _hash(normal), Connector.status == "pending")
    ).first()
    if connector is None or connector.code_expires_at < utcnow():
        raise ServiceError(
            "This code is not valid. Ask for a new one on the project's Import page; a code "
            f"works once, for {CODE_MINUTES} minutes.",
            400,
        )
    key = "lkc_" + secrets.token_urlsafe(32)
    connector.key_hash = _hash(key)
    connector.code_hash = None
    connector.code_expires_at = None
    connector.status = "active"
    connector.name = (name or "").strip()[:200] or "A computer with Tally"
    connector.last_seen_at = utcnow()
    session.commit()
    return connector, key


def by_key(session: Session, key: str | None) -> Connector:
    if not key:
        raise ServiceError("The connector's key is missing.", 401)
    connector = session.scalars(select(Connector).where(Connector.key_hash == _hash(key))).first()
    if connector is None or connector.status != "active":
        raise ServiceError("This connector has been unlinked. Link it again with a new code.", 401)
    return connector


def unlink(session: Session, connector: Connector) -> None:
    connector.status = "unlinked"
    connector.key_hash = None
    connector.code_hash = None
    session.commit()


def connectors_of(session: Session, project: Project) -> list[Connector]:
    return list(
        session.scalars(
            select(Connector)
            .where(Connector.project_id == project.id, Connector.status != "unlinked")
            .order_by(Connector.created_at)
        )
    )


def heartbeat(session: Session, connector: Connector, state: str | None, company: str | None):
    connector.last_seen_at = utcnow()
    connector.last_state = (state or "").strip()[:300] or None
    if company:
        connector.company = company.strip()[:200]
    session.commit()


def _body(data: bytes) -> str:
    """The XML of one Tally response, without its declaration, to sit inside another."""
    text = decode(data)
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("﻿"), count=1)


def combine(masters: bytes | None, vouchers: bytes | None) -> bytes:
    parts = [_body(x) for x in (masters, vouchers) if x]
    return ("<LEKHARACONNECTOR>" + "".join(parts) + "</LEKHARACONNECTOR>").encode("utf-8")


def sync(
    session: Session,
    storage: Storage,
    settings: Settings,
    connector: Connector,
    *,
    masters: bytes | None,
    vouchers: bytes | None,
    company: str | None,
) -> dict:
    project = session.get(Project, connector.project_id)
    org = session.get(Organization, connector.organization_id)
    if services.access_state(org, settings.as_of()) == "read_only":
        raise ServiceError(
            "The free month has ended, so Lekhara is not taking new data for this firm until it "
            "subscribes.",
            402,
        )
    if not masters and not vouchers:
        raise ServiceError("Nothing was sent.")
    if masters:
        connector.masters_key = storage.put(masters)
    elif connector.masters_key:
        masters = storage.get(connector.masters_key)
    data = combine(masters, vouchers)
    digest = hashlib.sha256(data).hexdigest()
    connector.last_seen_at = utcnow()
    if company:
        connector.company = company.strip()[:200]
    if digest == connector.last_hash and connector.last_import_id:
        connector.last_sync_at = utcnow()
        connector.last_state = None
        session.commit()
        return {"status": "unchanged", "import_id": connector.last_import_id}
    stamp = utcnow().strftime("%Y-%m-%d %H.%M")
    row = tally.upload(
        session, storage, project, filename=f"Tally connector {stamp}.xml", data=data, user_id=None
    )
    _, plan = tally.review(session, storage, row, settings.as_of())
    tally.apply(session, storage, row, as_of=settings.as_of(), user_id=None)
    waiting = [a.title for a in plan.alerts if a.level == "blocking"]
    connector = session.get(Connector, connector.id)
    connector.last_import_id = row.id
    connector.last_hash = digest
    connector.last_sync_at = utcnow()
    connector.last_state = None
    session.commit()
    return {
        "status": "applied",
        "import_id": row.id,
        "waiting": waiting,
        "message": "Brought in."
        + (f" Waiting for choices in Lekhara: {'; '.join(waiting)}." if waiting else ""),
    }


def config(connector: Connector, project: Project) -> dict:
    return {
        "project": project.name,
        "company": connector.company,
        "interval_seconds": INTERVAL_SECONDS,
        "recent_days": RECENT_DAYS,
        "full_sync_hours": FULL_SYNC_HOURS,
    }
