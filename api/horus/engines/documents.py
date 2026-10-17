"""The document vault: what a project should hold, what it holds, and what is about to lapse.

Every document is filed against the project and, where it belongs to one, a unit, a
case or a withdrawal. The checklist is the set of documents banks, K-RERA and buyers
ask for; record checks are the ones needed once per unit, case or withdrawal.
"""

import re
from dataclasses import dataclass
from datetime import date

CATEGORY_LABEL = {
    "registration": "K-RERA registration",
    "title": "Title and land",
    "agreement": "Agreements",
    "approval": "Approvals and NOCs",
    "bank": "Bank and escrow",
    "insurance": "Insurance and guarantees",
    "certificate": "Certificates",
    "sale_deed": "Sale deeds",
    "ekhata": "Khata",
    "order": "Orders and notices",
    "tax": "Tax",
    "invoice": "Bills and invoices",
    "other": "Other",
}

OWED_TO = {
    "approval": "Authority",
    "insurance": "Insurer",
    "bank": "Bank",
    "registration": "K-RERA",
}

LINK_TYPES = ("unit", "case", "withdrawal")


@dataclass(frozen=True)
class Requirement:
    key: str
    title: str
    category: str
    why: str
    tracks_expiry: bool = False


_REQUIREMENTS = (
    Requirement(
        "krera_registration",
        "K-RERA registration certificate",
        "registration",
        "Banks, buyers and K-RERA ask for it first.",
    ),
    Requirement(
        "title_deed",
        "Title deed and mother deed",
        "title",
        "Every lender's legal check starts here.",
    ),
    Requirement(
        "encumbrance",
        "Encumbrance certificate",
        "title",
        "Shows the land is free of charges. Lenders want a recent one.",
    ),
    Requirement(
        "jda",
        "Joint development agreement",
        "agreement",
        "Sets the landowners' share and the GST on development rights.",
    ),
    Requirement(
        "plan_sanction",
        "Building plan sanction",
        "approval",
        "The sanction is valid for a fixed period; building after it lapses is a violation.",
        tracks_expiry=True,
    ),
    Requirement(
        "commencement",
        "Commencement certificate",
        "approval",
        "Needed before construction starts.",
    ),
    Requirement(
        "environmental",
        "Environmental clearance",
        "approval",
        "Needed above 20,000 square metres of built-up area. Mark it not needed if yours "
        "is smaller.",
    ),
    Requirement(
        "fire_noc",
        "Fire NOC",
        "approval",
        "Needed for high-rise buildings, and again for the occupancy certificate.",
        tracks_expiry=True,
    ),
    Requirement(
        "escrow_letter",
        "Designated account letter from the bank",
        "bank",
        "Proves where the 70% of buyer money goes.",
    ),
    Requirement(
        "insurance",
        "Contractor's all-risk insurance",
        "insurance",
        "Lenders ask for it to be in force for the whole build.",
        tracks_expiry=True,
    ),
    Requirement(
        "oc",
        "Occupancy certificate",
        "approval",
        "Registration and possession depend on it.",
    ),
)

REQUIREMENTS = {r.key: r for r in _REQUIREMENTS}


def project_requirements(*, joint_development: bool, oc_received: bool) -> list[Requirement]:
    skip = set()
    if not joint_development:
        skip.add("jda")
    if not oc_received:
        skip.add("oc")
    return [r for r in _REQUIREMENTS if r.key not in skip]


@dataclass(frozen=True)
class HeldDocument:
    document_id: str
    title: str
    category: str
    requirement: str | None = None
    expires_on: date | None = None
    link_type: str | None = None
    link_id: str | None = None


@dataclass(frozen=True)
class ChecklistItem:
    requirement: Requirement
    status: str
    """held, missing, expiring, expired or waived."""
    document_id: str | None = None
    expires_on: date | None = None
    waiver_reason: str | None = None


@dataclass(frozen=True)
class RecordCheck:
    key: str
    title: str
    category: str
    link_type: str
    needed: int
    held: int
    missing: tuple[tuple[str, str], ...]
    """(record id, label) for each record without its document."""


@dataclass(frozen=True)
class Expiring:
    document_id: str
    title: str
    category: str
    expires_on: date
    expired: bool


def expiry_status(expires_on: date | None, *, as_of: date, notice_days: int) -> str:
    if expires_on is None:
        return "held"
    if expires_on < as_of:
        return "expired"
    if (expires_on - as_of).days <= notice_days:
        return "expiring"
    return "held"


def checklist(
    requirements: list[Requirement],
    held: list[HeldDocument],
    waivers: dict[str, str],
    *,
    as_of: date,
    notice_days: int,
) -> list[ChecklistItem]:
    """One line per requirement. The latest-expiring document filed against it counts."""
    items = []
    for r in requirements:
        matches = [h for h in held if h.requirement == r.key]
        if matches:
            best = max(matches, key=lambda h: h.expires_on or date.max)
            status = expiry_status(best.expires_on, as_of=as_of, notice_days=notice_days)
            items.append(ChecklistItem(r, status, best.document_id, best.expires_on))
        elif r.key in waivers:
            items.append(ChecklistItem(r, "waived", waiver_reason=waivers[r.key]))
        else:
            items.append(ChecklistItem(r, "missing"))
    return items


def record_check(
    key: str,
    title: str,
    category: str,
    link_type: str,
    records: list[tuple[str, str]],
    held: list[HeldDocument],
) -> RecordCheck:
    have = {h.link_id for h in held if h.category == category and h.link_type == link_type}
    missing = tuple((rid, label) for rid, label in records if rid not in have)
    return RecordCheck(
        key=key,
        title=title,
        category=category,
        link_type=link_type,
        needed=len(records),
        held=len(records) - len(missing),
        missing=missing,
    )


def expiring(held: list[HeldDocument], *, as_of: date, notice_days: int) -> list[Expiring]:
    out = []
    for h in held:
        status = expiry_status(h.expires_on, as_of=as_of, notice_days=notice_days)
        if status in ("expiring", "expired"):
            out.append(
                Expiring(h.document_id, h.title, h.category, h.expires_on, status == "expired")
            )
    return sorted(out, key=lambda e: e.expires_on)


# Search


@dataclass(frozen=True)
class Snippet:
    before: str
    match: str
    after: str


def snippets(text: str, query: str, *, width: int = 70, limit: int = 3) -> list[Snippet]:
    """Up to `limit` places where the query appears, with some words either side."""
    if not query.strip():
        return []
    flat = re.sub(r"\s+", " ", text)
    out = []
    for m in re.finditer(re.escape(query.strip()), flat, flags=re.IGNORECASE):
        start, end = m.start(), m.end()
        before = flat[max(0, start - width) : start]
        after = flat[end : end + width]
        if start - width > 0:
            before = "..." + before.split(" ", 1)[-1]
        if end + width < len(flat):
            after = after.rsplit(" ", 1)[0] + "..."
        out.append(Snippet(before, flat[start:end], after))
        if len(out) == limit:
            break
    return out
