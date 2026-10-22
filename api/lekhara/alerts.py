"""Emails that tell people at once about something they should know: a sign-in from a browser
not seen before, someone downloading everything, support opening the workspace."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.auth import OrgRole
from lekhara.config import Settings
from lekhara.mail import send_email
from lekhara.models import Membership, Organization, User, utcnow


def device(agent: str | None) -> str:
    """'Chrome on Windows' from a browser's user agent; 'An unknown browser' when unclear."""
    text = agent or ""
    browser = next(
        (
            name
            for pattern, name in (
                (r"Edg/", "Edge"),
                (r"OPR/|Opera", "Opera"),
                (r"Firefox/", "Firefox"),
                (r"Chrome/", "Chrome"),
                (r"Safari/", "Safari"),
            )
            if re.search(pattern, text)
        ),
        None,
    )
    system = next(
        (
            name
            for pattern, name in (
                (r"Android", "Android"),
                (r"iPhone|iPad", "iPhone or iPad"),
                (r"Windows", "Windows"),
                (r"Mac OS X|Macintosh", "a Mac"),
                (r"Linux", "Linux"),
            )
            if re.search(pattern, text)
        ),
        None,
    )
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "An unknown browser"


def new_sign_in(
    session: Session, settings: Settings, user: User, ip: str | None, agent: str | None
) -> None:
    when = utcnow().strftime("%d %b %Y, %H:%M UTC")
    send_email(
        session,
        settings,
        to=user.email,
        subject="A new sign-in to your Lekhara account",
        body=(
            f"Hello {user.name},\n\n"
            f"Someone signed in to your Lekhara account from {device(agent)}"
            f"{f' at the address {ip}' if ip else ''}, on {when}.\n\n"
            "If it was you, there is nothing to do. If it was not, reset your password now, then "
            "in Settings sign out everywhere else and turn on two-step sign-in."
        ),
        kind="alert_sign_in",
    )
    session.commit()


def tell_managers(
    session: Session,
    settings: Settings,
    org: Organization,
    *,
    subject: str,
    body: str,
    kind: str,
    except_user_id: str | None = None,
) -> None:
    """Emails the firm's owner and finance."""
    people = session.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == org.id,
            Membership.role.in_([OrgRole.OWNER.value, OrgRole.FINANCE.value]),
        )
    )
    for person in people:
        if person.id == except_user_id or not person.is_active:
            continue
        send_email(
            session,
            settings,
            to=person.email,
            subject=subject,
            body=f"Hello {person.name},\n\n{body}",
            kind=kind,
        )
    session.commit()
