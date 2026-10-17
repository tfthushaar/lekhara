"""Email.

Every message is kept in the outbox. It is sent over SMTP when `LEKHARA_SMTP_URL` is set
(for example smtp://user:password@smtp.example.com:587); otherwise it is written to the log,
which is how local development reads its sign-up, reset and invitation links.
"""

import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

from lekhara.config import Settings
from lekhara.models import OutboundEmail, utcnow

log = logging.getLogger("lekhara.mail")


def _deliver(settings: Settings, to: str, subject: str, body: str) -> None:
    url = urlparse(settings.smtp_url)
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    port = url.port or (465 if url.scheme == "smtps" else 587)
    server_class = smtplib.SMTP_SSL if url.scheme == "smtps" else smtplib.SMTP
    with server_class(url.hostname, port, timeout=20) as server:
        if url.scheme != "smtps":
            server.starttls()
        if url.username:
            server.login(unquote(url.username), unquote(url.password or ""))
        server.send_message(message)


def send_email(
    session: Session, settings: Settings, *, to: str, subject: str, body: str, kind: str
) -> OutboundEmail:
    row = OutboundEmail(to_address=to, subject=subject, body=body, kind=kind)
    session.add(row)
    if settings.smtp_url:
        try:
            _deliver(settings, to, subject, body)
            row.sent_at = utcnow()
        except (OSError, smtplib.SMTPException) as exc:
            row.error = str(exc)[:500]
            log.warning("Could not send %s email to %s: %s", kind, to, exc)
    else:
        log.warning("Email not sent (no SMTP set up). To %s: %s\n%s", to, subject, body)
    return row
