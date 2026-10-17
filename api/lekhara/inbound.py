"""The forwarding address: each project's own email address, and what comes in through it.

Anything sent or forwarded to <token>@<inbound domain> is kept, and each file in it is brought
in the way it would be if uploaded: a Tally export through the Tally import, a bank statement
through the bank statement import, a sheet of units, payments, suppliers, bills or orders
through the Import centre, and anything else into the document vault. What needs no choice is
applied by itself; what does waits for the builder, linked from the project's Import page.

Mail from the firm's own team, or from senders it trusts (a bank's statement service, the
accountant), is read at once. Mail from anyone else waits until a team member allows it, so
nobody can put records into a project by knowing its address.

Mail reaches Lekhara in either of two ways: an email service (SendGrid, Mailgun, Cloudflare
Email Routing or any other) posts each message to /inbound/email with the shared secret, or
Lekhara checks a catch-all mailbox over IMAP every two minutes.
"""

import contextlib
import email
import imaplib
import io
import logging
import re
import secrets
import zipfile
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from pathlib import PurePath
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import imports, jobs, services
from lekhara.bank import service as bank
from lekhara.bank.reader import read_statement
from lekhara.config import Settings
from lekhara.models import (
    InboundItem,
    InboundMessage,
    Membership,
    Project,
    TrustedSender,
    User,
)
from lekhara.records import RECORD_TYPES
from lekhara.services import ServiceError
from lekhara.storage import Storage
from lekhara.tally import service as tally
from lekhara.tally.reader import decode, detect

log = logging.getLogger("lekhara.inbound")

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
SIGNATURE_IMAGE_BYTES = 30_000
"""Small pictures in an email body are logos and signatures, not documents."""

CATEGORY_WORDS = (
    ("invoice", r"invoice|\bbill\b|\bra bill|tax invoice"),
    ("approval", r"\bnoc\b|approval|sanction|plan approval|commencement|clearance"),
    ("insurance", r"insurance|policy|guarantee|\bbg\b"),
    ("sale_deed", r"sale deed|deed of sale"),
    ("ekhata", r"khata"),
    ("agreement", r"agreement|\bjda\b|\bmou\b|contract"),
    ("registration", r"rera|registration certificate"),
    ("certificate", r"certificate|\bform \d"),
    ("bank", r"statement|\bbank\b|escrow"),
    ("order", r"\border\b|notice|summons|judgment"),
    ("tax", r"\bgst\b|\btds\b|\btax\b|26as|challan"),
    ("title", r"\btitle\b|encumbrance|\bec\b|mother deed|survey"),
)


# Addresses


def _new_token(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:24].strip("-") or "project"
    return f"{slug}-{''.join(secrets.choice(_ALPHABET) for _ in range(5))}"


def address_for(session: Session, project: Project, settings: Settings) -> str:
    """The project's forwarding address, made the first time it is asked for."""
    if not project.mail_token:
        while True:
            token = _new_token(project.name)
            if session.scalars(select(Project).where(Project.mail_token == token)).first() is None:
                break
        project.mail_token = token
        session.commit()
    return f"{project.mail_token}@{settings.inbound_domain}"


def _recipients(msg: EmailMessage, envelope: list[str]) -> list[str]:
    headers = []
    for name in ("To", "Cc", "Delivered-To", "X-Original-To", "X-Forwarded-To", "Envelope-To"):
        headers.extend(str(v) for v in msg.get_all(name, []))
    found = [a for _, a in getaddresses(list(envelope) + headers) if a]
    return [a.strip().casefold() for a in found]


def project_for(session: Session, addresses: list[str], domain: str) -> Project | None:
    domain = domain.casefold()
    for address in addresses:
        local, _, host = address.rpartition("@")
        if host != domain or not local:
            continue
        token = local.split("+", 1)[0]
        project = session.scalars(select(Project).where(Project.mail_token == token)).first()
        if project is not None:
            return project
    return None


# Who may send


def _failed_authentication(msg: EmailMessage) -> bool:
    """The receiving service's verdict, when it gives one: a sender whose domain did not sign
    or authorise the message is not taken at its word."""
    results = " ".join(str(v) for v in msg.get_all("Authentication-Results", [])).casefold()
    if not results:
        return False
    passed = re.search(r"\b(dkim|spf|dmarc)=pass", results)
    failed = re.search(r"\b(dkim|spf|dmarc)=(fail|softfail)", results)
    return bool(failed) and not passed


def trusted_senders(session: Session, organization_id: str) -> list[TrustedSender]:
    return list(
        session.scalars(
            select(TrustedSender)
            .where(TrustedSender.organization_id == organization_id)
            .order_by(TrustedSender.address)
        )
    )


def is_trusted(session: Session, organization_id: str, address: str) -> bool:
    address = address.casefold()
    team = session.scalars(
        select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id)
    )
    if address in {e.casefold() for e in team}:
        return True
    domain = "@" + address.rpartition("@")[2]
    return any(t.address in (address, domain) for t in trusted_senders(session, organization_id))


def add_trusted(session: Session, organization_id: str, address: str, *, user_id) -> TrustedSender:
    address = address.strip().casefold()
    if not re.fullmatch(r"([^@\s]+@|@)[^@\s]+\.[^@\s]+", address):
        raise ServiceError("Enter an email address, or a whole domain written as @bank.example.")
    existing = session.scalars(
        select(TrustedSender).where(
            TrustedSender.organization_id == organization_id, TrustedSender.address == address
        )
    ).first()
    if existing is not None:
        return existing
    row = TrustedSender(organization_id=organization_id, address=address, added_by_user_id=user_id)
    session.add(row)
    return row


# Receiving


def _attachments(msg: EmailMessage) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for n, part in enumerate(msg.walk(), start=1):
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").casefold()
        if not filename and disposition != "attachment":
            continue
        data = part.get_payload(decode=True) or b""
        if not data:
            continue
        if (
            part.get_content_maintype() == "image"
            and disposition != "attachment"
            and len(data) < SIGNATURE_IMAGE_BYTES
        ):
            continue
        files.append((filename or f"attachment-{n}", data))
    return files


def receive(
    session: Session,
    storage: Storage,
    settings: Settings,
    raw: bytes,
    *,
    envelope_to: list[str] = (),
) -> InboundMessage | None:
    """Keep an incoming email and its files. None when it is not for any project."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    project = project_for(session, _recipients(msg, list(envelope_to)), settings.inbound_domain)
    if project is None:
        return None
    name, sender = parseaddr(str(msg.get("From", "")))
    sender = sender.casefold()
    trusted = bool(sender) and not _failed_authentication(msg)
    trusted = trusted and is_trusted(session, project.organization_id, sender)
    message = InboundMessage(
        organization_id=project.organization_id,
        project_id=project.id,
        from_address=sender[:320] or "unknown",
        from_name=(name or None) and name[:200],
        subject=str(msg.get("Subject", "") or "")[:500] or None,
        storage_key=storage.put(raw),
        trusted=trusted,
        status="queued" if trusted else "held",
    )
    session.add(message)
    session.flush()
    files = _attachments(msg)
    limit = settings.tally_upload_mb * 1_000_000
    for filename, data in files:
        too_big = len(data) > limit
        session.add(
            InboundItem(
                message_id=message.id,
                filename=_safe(filename),
                size=len(data),
                storage_key=storage.put(data) if not too_big else "",
                status="ignored" if too_big else "queued",
                note=f"Larger than {settings.tally_upload_mb} MB." if too_big else None,
            )
        )
    if not files:
        message.status = "done"
        message.note = "No files were attached, so there was nothing to bring in."
    elif trusted:
        jobs.enqueue(session, "inbound.process", {"message_id": message.id})
    else:
        message.note = (
            f"{sender or 'The sender'} is not in your team or your trusted senders, so this "
            "waits until someone in your team allows it."
        )
    session.commit()
    return message


def _safe(filename: str) -> str:
    name = PurePath(filename.replace("\\", "/")).name.strip() or "attachment"
    return re.sub(r"[\x00-\x1f]", "", name)[:300]


def allow(
    session: Session,
    organization_id: str,
    message: InboundMessage,
    *,
    user_id: str | None,
    trust: bool,
) -> None:
    if message.status != "held":
        raise ServiceError("This email is not waiting for anyone.")
    message.status = "queued"
    message.trusted = True
    message.decided_by_user_id = user_id
    message.note = None
    if trust and message.from_address and message.from_address != "unknown":
        add_trusted(session, organization_id, message.from_address, user_id=user_id)
    jobs.enqueue(session, "inbound.process", {"message_id": message.id})
    session.commit()


def reject(session: Session, message: InboundMessage, *, user_id: str | None) -> None:
    if message.status != "held":
        raise ServiceError("This email is not waiting for anyone.")
    message.status = "rejected"
    message.decided_by_user_id = user_id
    message.note = "Turned away; nothing in it was brought in."
    for item in items_of(session, message):
        if item.status == "queued":
            item.status = "ignored"
    session.commit()


def items_of(session: Session, message: InboundMessage) -> list[InboundItem]:
    return list(
        session.scalars(
            select(InboundItem).where(InboundItem.message_id == message.id).order_by(InboundItem.id)
        )
    )


def messages_of(session: Session, project: Project, limit: int = 20) -> list[InboundMessage]:
    return list(
        session.scalars(
            select(InboundMessage)
            .where(InboundMessage.project_id == project.id)
            .order_by(InboundMessage.received_at.desc())
            .limit(limit)
        )
    )


# Reading each file


def classify(filename: str, data: bytes) -> str:
    """tally, sheet, pdf or document."""
    kind = detect(filename, data)
    if kind in ("xml", "json"):
        head = decode(data[:20000]).casefold()
        if "tallymessage" in head or "<envelope" in head or "tallyrequest" in head:
            return "tally"
        return "document"
    if kind == "xlsx":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return "document"
        return "sheet" if any(n.startswith("xl/") for n in names) else "document"
    if kind in ("xls", "html", "text"):
        return (
            "sheet"
            if PurePath(filename).suffix.casefold() != ".txt" or b"," in data[:4000]
            else "document"
        )
    if kind == "pdf":
        return "pdf"
    return "document"


def _category(text: str) -> str:
    lowered = text.casefold()
    for category, pattern in CATEGORY_WORDS:
        if re.search(pattern, lowered):
            return category
    return "other"


def best_record(filename: str, data: bytes) -> str | None:
    """Which kind of record a sheet holds, from its column names, if any fits."""
    try:
        rows = imports.read_rows(filename, data)
    except ServiceError:
        return None
    if not rows:
        return None
    best, best_score = None, 0
    for kind, record in RECORD_TYPES.items():
        header = rows[imports.find_header(record, rows)]
        matched = set(imports.match_columns(record, [str(v) for v in header]).values())
        required = {f.key for f in record.fields if f.required}
        if not required <= matched or len(matched) < 2:
            continue
        score = len(matched) + len(required)
        if score > best_score:
            best, best_score = kind, score
    return best


def _as_document(session, storage, settings, project, message, item, data) -> None:
    doc = services.store_document(
        session,
        storage,
        project,
        data=data,
        filename=item.filename,
        fields={
            "category": _category(f"{item.filename} {message.subject or ''}"),
            "notes": f"Sent by {message.from_address}"
            + (f": {message.subject}" if message.subject else ""),
        },
        max_bytes=settings.max_upload_mb * 1_000_000,
    )
    item.kind = "document"
    item.status, item.result_type, item.result_id = "done", "document", doc.id
    item.note = f'Filed in the documents as "{doc.title}".'


def _statement(session, storage, settings, project, item, data) -> bool:
    """Bring a bank statement in; False when the file is not one."""
    from lekhara.bank.pdf import PasswordNeeded

    passwords = bank.statement_passwords(session, settings, project.organization_id)
    try:
        read_statement(item.filename, data, passwords)
    except PasswordNeeded as exc:
        item.kind, item.status, item.note = "bank_statement", "review", str(exc)
        return True
    except ServiceError:
        return False
    row = bank.upload(
        session,
        storage,
        project,
        filename=item.filename,
        data=data,
        user_id=None,
        passwords=passwords,
    )
    item.kind, item.result_type, item.result_id = "bank_statement", "bank_statement", row.id
    _, plan = bank.review(session, storage, row, settings.as_of(), passwords)
    blocking = [a.title for a in plan.alerts if a.level == "blocking"]
    if not bank.options(row).get("role"):
        item.status = "review"
        item.note = "A bank statement: say once which account it is, and it comes in."
    elif blocking:
        bank.apply(session, storage, row, as_of=settings.as_of(), user_id=None, passwords=passwords)
        item.status = "review"
        item.note = f"Brought in, except what waits for you: {'; '.join(blocking)}."
    else:
        bank.apply(session, storage, row, as_of=settings.as_of(), user_id=None, passwords=passwords)
        item.status = "done"
        item.note = f"Bank statement brought in: {plan.counts.get('to_add', 0)} transactions."
    return True


def _tally(session, storage, settings, project, item, data) -> None:
    row = tally.upload(session, storage, project, filename=item.filename, data=data, user_id=None)
    item.kind, item.result_type, item.result_id = "tally", "tally_import", row.id
    _, plan = tally.review(session, storage, row, settings.as_of())
    blocking = [a.title for a in plan.alerts if a.level == "blocking"]
    if blocking:
        item.status = "review"
        item.note = f"A Tally export waiting for your choices: {'; '.join(blocking)}."
        return
    tally.apply(session, storage, row, as_of=settings.as_of(), user_id=None)
    item.status = "done"
    item.note = "Tally export brought in."


def route(
    session: Session,
    storage: Storage,
    settings: Settings,
    project: Project,
    message: InboundMessage,
    item: InboundItem,
) -> None:
    data = storage.get(item.storage_key)
    kind = classify(item.filename, data)
    item.kind = kind
    if kind == "tally":
        _tally(session, storage, settings, project, item, data)
    elif kind == "sheet":
        if _statement(session, storage, settings, project, item, data):
            return
        record = best_record(item.filename, data)
        if record is None:
            _as_document(session, storage, settings, project, message, item, data)
            return
        batch = imports.start(
            session, project, record, filename=item.filename, data=data, user_id=None
        )
        item.kind, item.result_type, item.result_id = "sheet", "import_batch", batch.id
        item.status = "review"
        item.note = (
            f"A sheet of {RECORD_TYPES[record].title.lower()}: check the preview to import it."
        )
    elif kind == "pdf":
        from lekhara.bank.pdf import looks_like_statement

        if looks_like_statement(data) and _statement(
            session, storage, settings, project, item, data
        ):
            return
        _as_document(session, storage, settings, project, message, item, data)
    else:
        _as_document(session, storage, settings, project, message, item, data)


def retry(session: Session, storage: Storage, settings: Settings, item: InboundItem) -> InboundItem:
    """Read a file again, such as a statement once its password has been given."""
    message = session.get(InboundMessage, item.message_id)
    if not message.trusted:
        raise ServiceError("Allow the email first.")
    if item.status not in ("failed", "review") or item.result_id:
        raise ServiceError("This file has already been brought in.")
    item.status, item.note = "queued", None
    project = session.get(Project, message.project_id)
    try:
        route(session, storage, settings, project, message, item)
    except ServiceError as exc:
        session.rollback()
        item = session.get(InboundItem, item.id)
        item.status, item.note = "failed", str(exc)[:500]
    session.commit()
    return item


def process(session: Session, storage: Storage, settings: Settings, message_id: str) -> None:
    message = session.get(InboundMessage, message_id)
    if message is None or message.status not in ("queued",):
        return
    project = session.get(Project, message.project_id)
    items = [i for i in items_of(session, message) if i.status == "queued"]
    for item in items:
        try:
            route(session, storage, settings, project, message, item)
        except ServiceError as exc:
            session.rollback()
            item = session.get(InboundItem, item.id)
            item.status = "failed"
            item.note = str(exc)[:500]
        session.commit()
    message = session.get(InboundMessage, message_id)
    states = {i.status for i in items_of(session, message)}
    message.status = "failed" if states == {"failed"} else "done"
    session.commit()


@jobs.handler("inbound.process")
def _process_job(ctx: jobs.Context, payload: dict) -> None:
    process(ctx.session, ctx.storage, ctx.settings, payload["message_id"])


# A catch-all mailbox, checked every two minutes when one is set up


def _mailbox(url: str) -> tuple[str, int, str, str, str, bool]:
    parts = urlparse(url)
    if parts.scheme not in ("imap", "imaps"):
        raise ValueError("The mailbox address should start with imap:// or imaps://")
    secure = parts.scheme == "imaps"
    return (
        parts.hostname or "",
        parts.port or (993 if secure else 143),
        unquote(parts.username or ""),
        unquote(parts.password or ""),
        unquote(parts.path.lstrip("/")) or "INBOX",
        secure,
    )


@jobs.handler("inbound.poll_imap")
def _poll_imap(ctx: jobs.Context, payload: dict) -> None:
    host, port, user, password, folder, secure = _mailbox(ctx.settings.inbound_imap_url or "")
    client = imaplib.IMAP4_SSL(host, port) if secure else imaplib.IMAP4(host, port)
    try:
        client.login(user, password)
        client.select(folder)
        _, found = client.search(None, "UNSEEN")
        for number in (found[0] or b"").split():
            _, fetched = client.fetch(number, "(RFC822)")
            raw = next((part[1] for part in fetched if isinstance(part, tuple)), None)
            if raw:
                receive(ctx.session, ctx.storage, ctx.settings, raw)
            client.store(number, "+FLAGS", "\\Seen")
    finally:
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            client.logout()


jobs.every("inbound.poll_imap", 120, lambda s: bool(s.inbound_imap_url))
