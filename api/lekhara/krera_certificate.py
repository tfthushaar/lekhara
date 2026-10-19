"""Reading a project's details from its K-RERA registration certificate (Form C), so a builder
adds a project by dropping in the certificate rather than typing it.

The certificate's typed text gives the registration number, the project's name, where it is,
the promoter, and the validity period, which runs from the registration date to the completion
date the promoter declared. A scanned certificate has no text to read yet; the builder types the
details instead.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from lekhara.pdf import read_pages
from lekhara.records import UNITS, ParseError, parse_value
from lekhara.services import ServiceError

_REGISTRATION = re.compile(r"\bPRM\s*/\s*KA\s*/\s*RERA\s*/[A-Z0-9/ ]*[A-Z0-9]", re.IGNORECASE)
_DATE = r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4})"
_VALIDITY = re.compile(
    rf"(?:commencing|starting)\s+from\s+{_DATE}\s+(?:and\s+)?(?:ending|end)\s+(?:with|on)\s+{_DATE}",
    re.IGNORECASE,
)
_FROM_TO = re.compile(rf"valid\w*\s+(?:for\s+a\s+period\s+)?from\s+{_DATE}\s+to\s+{_DATE}", re.I)
_PROJECT = re.compile(
    r"(?:Name\s+of\s+the\s+project|Project\s+name|Project)\s*[:\-]\s*(.+?)"
    r"(?=,|\s+(?:Plot|Sy\.?|Survey|situated|located|at\s|having|bearing)\b|\n|$)",
    re.IGNORECASE,
)
_SITUATED = re.compile(r"(?:situated|located)\s+at\s+(.+?)(?:\.|\n|$)", re.IGNORECASE)
_PROMOTER = re.compile(
    r"(?:^|\n)\s*1\.\s*(.+?)\s+having\s+its\s+(?:registered|principal)", re.IGNORECASE | re.S
)
_PROMOTER_LABEL = re.compile(r"(?:Name\s+of\s+the\s+)?Promoter\s*[:\-]\s*(.+?)(?:,|\n|$)", re.I)


@dataclass
class Reading:
    fields: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .,;:-")


def _day(text: str) -> date | None:
    try:
        return parse_value(UNITS.field("booked_on"), _clean(text).replace(",", ""))
    except ParseError:
        return None


def read_text(text: str) -> Reading:
    flat = re.sub(r"[ \t]+", " ", text)
    out = Reading()
    reg = _REGISTRATION.search(flat)
    if reg:
        out.fields["krera_registration"] = re.sub(r"\s+", "", reg.group(0)).upper()
    period = _VALIDITY.search(flat) or _FROM_TO.search(flat)
    if period:
        start, end = _day(period.group(1)), _day(period.group(2))
        if start:
            out.fields["registered_on"] = start.isoformat()
        if end and (start is None or end > start):
            out.fields["possession_due_on"] = end.isoformat()
    name = _PROJECT.search(flat)
    if name and _clean(name.group(1)):
        out.fields["name"] = _clean(name.group(1))[:200]
    where = _SITUATED.search(flat)
    if where:
        parts = [p.strip() for p in where.group(1).split(",") if p.strip()]
        city = next((p for p in parts if re.search(r"bengaluru|bangalore", p, re.I)), None)
        town = [p for p in parts if p is not city and not re.search(r"\d{6}|karnataka", p, re.I)]
        if town:
            out.fields["locality"] = _clean(town[-1])[:200]
        if city:
            out.fields["city"] = "Bengaluru"
    promoter = _PROMOTER.search(flat) or _PROMOTER_LABEL.search(flat)
    if promoter and _clean(promoter.group(1)):
        out.fields["spv_name"] = _clean(promoter.group(1))[:200]
    labels = {
        "name": "the project's name",
        "krera_registration": "the registration number",
        "registered_on": "the registration date",
        "possession_due_on": "the completion date",
    }
    out.missing = [label for key, label in labels.items() if key not in out.fields]
    return out


def read_certificate(filename: str, data: bytes) -> Reading:
    if not filename.casefold().endswith(".pdf"):
        raise ServiceError("The certificate is read from its PDF. Choose the PDF K-RERA issued.")
    pages = read_pages(data)
    if pages is None:
        raise ServiceError("This file could not be opened as a PDF.")
    text = "\n".join(pages)
    if len(text.strip()) < 40:
        raise ServiceError(
            "This looks like a scanned copy, which has no text to read yet. Type the details "
            "below; they are on the certificate."
        )
    reading = read_text(text)
    if "krera_registration" not in reading.fields:
        raise ServiceError(
            "No K-RERA registration number was found in this file. Is it the project's "
            "registration certificate?"
        )
    return reading
