"""A record of each certificate's signing, and a way for the bank to check what was signed.

When the architect, engineer or CA signs a withdrawal certificate in Lekhara, Lekhara keeps who
signed (their account and its email), when, from which address and browser, whether they use
two-step sign-in, and a fingerprint (SHA-256) of exactly what they signed: the project, the
request, the statement with its figures, and the signer. Entering the figures is recorded the
same way. The certificate's PDF ends with a signing record page carrying all of it and a check
code; anyone holding the PDF, the bank first, can enter the code on Lekhara's check page and see
what was signed. A figure altered in the PDF afterwards no longer agrees with it.

The idea comes from DocuSeal and Documenso, whose signed documents end with an audit page. A
seal that a PDF reader checks by itself needs a document-signing certificate from a certifying
authority (decision 36), and Aadhaar eSign needs a provider; both come later.
"""

import base64
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.alerts import device
from lekhara.engines.escrow import ROLE_LABEL, CertifierRole
from lekhara.models import (
    CertificateEvent,
    Project,
    User,
    WithdrawalCertificate,
    WithdrawalRequest,
    utcnow,
)
from lekhara.packs import STATEMENT, rupees, when

IST = timezone(timedelta(hours=5, minutes=30), "IST")
VERSION = "Lekhara certificate, version 1"


def _figure(value) -> str:
    return "not given" if value is None else str(value)


def statement(project: Project, row: WithdrawalCertificate) -> str:
    role = CertifierRole(row.role)
    return STATEMENT[role].format(
        project=project.name,
        on=when(row.issued_on),
        pct=f"{row.completion_pct}%" if row.completion_pct is not None else "not given",
        dev=rupees(row.development_cost_incurred),
        total=rupees(row.total_cost_incurred),
        draw=rupees(row.withdrawable_amount),
    )


def content(project: Project, request: WithdrawalRequest, row: WithdrawalCertificate) -> str:
    """Exactly what a signer signs, as the text whose fingerprint is kept."""
    role = CertifierRole(row.role)
    return "\n".join(
        [
            VERSION,
            f"Project: {project.name}",
            f"K-RERA registration: {project.krera_registration}",
            f"Withdrawal request: {request.id}",
            f"Amount requested: {request.amount}",
            f"Certificate of the {ROLE_LABEL[role].lower()}",
            statement(project, row),
            f"Physical completion: {_figure(row.completion_pct)}",
            f"Development cost incurred: {_figure(row.development_cost_incurred)}",
            f"Total cost incurred and paid: {_figure(row.total_cost_incurred)}",
            f"Amount that can be withdrawn: {_figure(row.withdrawable_amount)}",
            f"Signed by: {row.signer_name}, {row.signer_firm}",
            f"Issued on: {row.issued_on.isoformat() if row.issued_on else ''}",
        ]
    )


def fingerprint(project: Project, request: WithdrawalRequest, row: WithdrawalCertificate) -> str:
    return hashlib.sha256(content(project, request, row).encode("utf-8")).hexdigest()


def new_check_code() -> str:
    """Sixteen letters and digits in fours, easy to read out and type: 80 bits, not guessable."""
    raw = base64.b32encode(secrets.token_bytes(10)).decode()
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def normal_code(text: str) -> str:
    raw = re.sub(r"[^A-Z2-7]", "", (text or "").upper())
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4)) if len(raw) == 16 else ""


def record(
    session: Session,
    request: WithdrawalRequest,
    row: WithdrawalCertificate,
    action: str,
    *,
    user_id: str | None,
    ip: str | None,
    agent: str | None,
    two_step: bool,
    confirmed: bool,
) -> CertificateEvent:
    """Adds an event to the certificate's record (figures entered, or signed), with the
    fingerprint of the certificate as it then stood. The caller commits."""
    project = session.get(Project, request.project_id)
    user = session.get(User, user_id) if user_id else None
    event = CertificateEvent(
        request_id=request.id,
        role=row.role,
        action=action,
        user_id=user_id,
        name=(user.name if user else "")[:200],
        email=(user.email if user else "")[:320],
        ip=(ip or "")[:64] or None,
        device=device(agent)[:100] if agent else None,
        two_step=two_step,
        confirmed=confirmed,
        fingerprint=fingerprint(project, request, row),
    )
    session.add(event)
    return event


def seal(session: Session, request: WithdrawalRequest, row: WithdrawalCertificate) -> None:
    """At signing: the fingerprint of what was signed, and a check code for the bank."""
    project = session.get(Project, request.project_id)
    row.fingerprint = fingerprint(project, request, row)
    row.signed_at = utcnow()
    while row.check_code is None:
        code = new_check_code()
        taken = session.scalars(
            select(WithdrawalCertificate.id).where(WithdrawalCertificate.check_code == code)
        ).first()
        if taken is None:
            row.check_code = code


def events(session: Session, request: WithdrawalRequest, role: str) -> list[CertificateEvent]:
    return list(
        session.scalars(
            select(CertificateEvent)
            .where(CertificateEvent.request_id == request.id, CertificateEvent.role == role)
            .order_by(CertificateEvent.at)
        )
    )


def ist(moment: datetime | None) -> str:
    if moment is None:
        return "Not known"
    local = moment.replace(tzinfo=UTC).astimezone(IST)
    return f"{local.day} {local:%B %Y}, {local:%H:%M} IST"


def _who(e: CertificateEvent) -> str:
    who = f"{e.name} ({e.email})" if e.email else e.name or "Someone"
    where = ", ".join(x for x in (f"address {e.ip}" if e.ip else "", e.device or "") if x)
    return f"{who}{f', from {where}' if where else ''}"


def summary(session: Session, request: WithdrawalRequest, row: WithdrawalCertificate) -> dict:
    """The signing record as the withdrawal page shows it."""
    signed = next((e for e in events(session, request, row.role) if e.action == "signed"), None)
    project = session.get(Project, request.project_id)
    return {
        "kept": row.check_code is not None,
        "signed_at": row.signed_at.replace(microsecond=0).isoformat() if row.signed_at else None,
        "signed_at_label": ist(row.signed_at) if row.signed_at else None,
        "fingerprint": row.fingerprint,
        "check_code": row.check_code,
        "two_step": signed.two_step if signed else None,
        "from": _who(signed) if signed else None,
        "unchanged": row.fingerprint == fingerprint(project, request, row)
        if row.fingerprint
        else None,
    }


def record_page(
    session: Session, request: WithdrawalRequest, row: WithdrawalCertificate, check_url: str
) -> list[str]:
    """The signing record page that follows a certificate in its PDF and in the pack."""
    from lekhara.pdf import FIXED, HEADING

    role = CertifierRole(row.role)
    project = session.get(Project, request.project_id)
    page = [
        f"{HEADING}Signing record",
        f"Certificate of the {ROLE_LABEL[role].lower()}, {project.name}, K-RERA registration "
        f"{project.krera_registration}. Withdrawal of {rupees(request.amount)} requested.",
        "",
    ]
    if not row.signed:
        return [*page, "Not signed yet."]
    if row.check_code is None:
        return [
            *page,
            f"Signed by {row.signer_name} of {row.signer_firm} on {when(row.issued_on)}, before "
            "Lekhara kept signing records; no record is held for it.",
        ]
    trail = events(session, request, row.role)
    signed = next((e for e in trail if e.action == "signed"), None)
    rows = [
        ("Signed by", f"{row.signer_name}, {row.signer_firm}"),
        ("Their Lekhara account", signed.email if signed and signed.email else "Not known"),
        ("Signed at", ist(row.signed_at)),
        ("From", ", ".join(x for x in ((signed.ip or "") if signed else "",
                                         (signed.device or "") if signed else "") if x)
         or "Not known"),
        ("Two-step sign-in", "Yes" if signed and signed.two_step else "No"),
        ("Identity confirmed", "Within 15 minutes before signing"
         if signed and signed.confirmed else "Not known"),
        ("Check code", row.check_code),
    ]  # fmt: skip
    width = 86
    for label, value in rows:
        space = width - len(value) - 2
        page.append(f"{FIXED}{label} {'.' * max(space - len(label), 1)} {value}")
    page += [
        "",
        "Fingerprint of what was signed (SHA-256):",
        f"{FIXED}{row.fingerprint[:32]}",
        f"{FIXED}{row.fingerprint[32:]}",
        "",
        f"To check this certificate, open {check_url} and enter the check code. The page shows "
        "what was signed and by whom; if any figure in this document differs from it, the "
        "document was changed after signing.",
        "",
        f"{HEADING}History",
    ]
    for e in trail:
        what = "Signed" if e.action == "signed" else "Figures entered"
        page.append(f"{ist(e.at)}: {what} by {_who(e)}.")
    return page


def check(session: Session, code: str) -> dict | None:
    """What the public check page shows for a code, or None for a code that is not known."""
    code = normal_code(code)
    if not code:
        return None
    row = session.scalars(
        select(WithdrawalCertificate).where(WithdrawalCertificate.check_code == code)
    ).first()
    if row is None or not row.signed:
        return None
    request = session.get(WithdrawalRequest, row.request_id)
    project = session.get(Project, request.project_id)
    role = CertifierRole(row.role)
    return {
        "code": code,
        "certificate": f"Certificate of the {ROLE_LABEL[role].lower()}",
        "project": project.name,
        "krera_registration": project.krera_registration,
        "promoter": project.organization.legal_name or project.organization.name,
        "amount_requested": rupees(request.amount),
        "statement": statement(project, row),
        "signer_name": row.signer_name,
        "signer_firm": row.signer_firm,
        "issued_on": when(row.issued_on),
        "signed_at": ist(row.signed_at),
        "fingerprint": row.fingerprint,
        "unchanged": row.fingerprint == fingerprint(project, request, row),
        "released": request.released_on is not None,
    }
