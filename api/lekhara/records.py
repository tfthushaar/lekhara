"""What each kind of record holds, and how a value typed in a form or found in a spreadsheet
cell becomes a clean one.

One definition per record type drives the add and edit forms, the import template, the
import itself and the export, so the four always agree. Parsing is forgiving in the ways
builders' spreadsheets need: amounts like "1,20,00,000", "1.2 Cr" or "45 lakh", dates in
day-first Indian order, and yes or no written any way.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    """The column header in templates and exports."""
    kind: str
    """text, int, money, date, choice or bool."""
    required: bool = False
    aliases: tuple[str, ...] = ()
    choices: tuple[tuple[str, str], ...] = ()
    """(value, label) pairs for a choice."""
    help: str = ""
    example: str = ""


@dataclass(frozen=True)
class RecordType:
    kind: str
    title: str
    key: str
    """The field that identifies a record, so the same file imported twice changes nothing."""
    fields: tuple[Field, ...]

    def field(self, key: str) -> Field:
        return next(f for f in self.fields if f.key == key)


UNITS = RecordType(
    kind="units",
    title="Units and buyers",
    key="label",
    fields=(
        Field(
            "label",
            "Unit",
            "text",
            required=True,
            aliases=("unit no", "unit number", "flat", "flat no", "flat number", "apartment"),
            help="The unit number as on the K-RERA registration. Each unit appears once.",
            example="A-0101",
        ),
        Field(
            "tower",
            "Tower",
            "text",
            aliases=("block", "wing", "building"),
            example="Tower A",
        ),
        Field(
            "carpet_area_sqft",
            "Carpet area (sq ft)",
            "int",
            required=True,
            aliases=("carpet area", "carpet", "rera carpet area", "area"),
            help="RERA carpet area in square feet.",
            example="1150",
        ),
        Field(
            "owner_share",
            "Share",
            "choice",
            aliases=("owner", "owner share", "allotted to", "jda share"),
            choices=(("developer", "Developer"), ("landowner", "Landowner")),
            help="Whose share the unit falls in under a joint development. Developer if blank.",
            example="Developer",
        ),
        Field(
            "list_price",
            "List price",
            "money",
            aliases=("price", "basic price", "base price", "list value"),
            help="Rupees. Amounts like 1.2 crore or 95 lakh are understood.",
            example="9500000",
        ),
        Field(
            "guidance_value",
            "Guidance value",
            "money",
            aliases=("guidance", "government value", "market value as per guidance"),
            help="The unit's value at the government guidance rate, in rupees.",
            example="8800000",
        ),
        Field(
            "buyer_name",
            "Buyer",
            "text",
            aliases=("buyer name", "customer", "customer name", "allottee", "purchaser", "client"),
            help="Leave blank for an unsold unit.",
            example="Priya Sharma",
        ),
        Field(
            "buyer_phone",
            "Buyer phone",
            "text",
            aliases=("phone", "mobile", "contact", "customer phone", "mobile number"),
            example="9845012345",
        ),
        Field(
            "buyer_email",
            "Buyer email",
            "text",
            aliases=("email", "customer email", "email id"),
            example="priya@example.com",
        ),
        Field(
            "booked_on",
            "Booked on",
            "date",
            aliases=("booking date", "date of booking", "booked date", "allotment date"),
            help="Day first, as in 15/03/2025. Needed for a sold unit.",
            example="15/03/2025",
        ),
        Field(
            "agreement_value",
            "Agreement value",
            "money",
            aliases=(
                "sale value",
                "agreement amount",
                "total consideration",
                "consideration",
                "sale price",
            ),
            help="The price in the agreement for sale, before GST. Needed for a sold unit.",
            example="9200000",
        ),
    ),
)

RECEIPTS = RecordType(
    kind="receipts",
    title="Buyer payments",
    key="unit",
    fields=(
        Field(
            "unit",
            "Unit",
            "text",
            required=True,
            aliases=("unit no", "unit number", "flat", "flat no", "flat number"),
            help="The unit the payment is for, as in Lekhara.",
            example="A-0101",
        ),
        Field(
            "received_on",
            "Received on",
            "date",
            required=True,
            aliases=(
                "date",
                "receipt date",
                "payment date",
                "value date",
                "date of receipt",
                "credit date",
            ),
            help="Day first, as in 05/06/2025.",
            example="05/06/2025",
        ),
        Field(
            "amount",
            "Amount received",
            "money",
            required=True,
            aliases=(
                "amount",
                "received",
                "receipt amount",
                "credit",
                "credit amount",
                "amount received (rs)",
            ),
            help="What reached your bank, in rupees.",
            example="495000",
        ),
        Field(
            "tds_deducted",
            "TDS deducted",
            "money",
            aliases=("tds", "tds amount", "tds 194ia", "tds deducted by buyer"),
            help="TDS the buyer deducted under s.194IA, if any.",
            example="5000",
        ),
        Field(
            "reference",
            "Reference",
            "text",
            aliases=(
                "utr",
                "utr no",
                "cheque no",
                "cheque number",
                "reference no",
                "ref no",
                "transaction id",
                "instrument no",
            ),
            help="UTR, cheque number or receipt number.",
            example="HDFCN52025060512345",
        ),
    ),
)

RECORD_TYPES = {UNITS.kind: UNITS, RECEIPTS.kind: RECEIPTS}


def normalise_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()


def match_columns(record: RecordType, headers: list[str]) -> dict[int, str]:
    """Column index to field key, by the field's label, key or one of its aliases."""
    names: dict[str, str] = {}
    for f in record.fields:
        for name in (f.label, f.key.replace("_", " "), *f.aliases):
            names.setdefault(normalise_header(name), f.key)
    mapping: dict[int, str] = {}
    used: set[str] = set()
    for i, header in enumerate(headers):
        key = names.get(normalise_header(header))
        if key and key not in used:
            mapping[i] = key
            used.add(key)
    return mapping


# Parsing one value


class ParseError(ValueError):
    pass


def _money(raw: object) -> Decimal:
    if isinstance(raw, int | float | Decimal):
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    text = str(raw).casefold().replace(",", "").replace("/-", "").strip()
    text = re.sub(r"^(₹|rs\.?|inr)\s*", "", text).strip()
    factor = Decimal(1)
    for suffix, multiplier in (
        ("crores", 10**7),
        ("crore", 10**7),
        ("cr", 10**7),
        ("lakhs", 10**5),
        ("lakh", 10**5),
        ("lacs", 10**5),
        ("lac", 10**5),
        ("l", 10**5),
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            factor = Decimal(multiplier)
            break
    try:
        value = Decimal(text) * factor
    except InvalidOperation:
        raise ParseError("is not an amount") from None
    if value < 0:
        raise ParseError("cannot be negative")
    return value.quantize(Decimal("0.01"))


def _date(raw: object) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip().casefold()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ t].*)?", text)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[/.\- ](\d{1,2}|[a-z]{3,9})[/.\- ](\d{2,4})", text)
        if not m:
            raise ParseError("is not a date; write it day first, as in 15/03/2025")
        d, month, y = m.groups()
        d, y = int(d), int(y)
        mo = int(month) if month.isdigit() else _MONTHS.get(month[:3], 0)
        if y < 100:
            y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        raise ParseError("is not a real date") from None


def _bool(raw: object) -> bool:
    text = str(raw).strip().casefold()
    if text in ("yes", "y", "true", "1", "booked", "sold"):
        return True
    if text in ("no", "n", "false", "0", "unsold", "available"):
        return False
    raise ParseError("should be yes or no")


def parse_value(field: Field, raw: object):
    """The clean value, or None for a blank cell. Raises ParseError with plain words."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if field.kind == "text":
        text = str(raw).strip()
        if isinstance(raw, float) and raw.is_integer():
            text = str(int(raw))
        return text
    if field.kind == "int":
        try:
            value = Decimal(str(raw).replace(",", "").strip())
        except InvalidOperation:
            raise ParseError("is not a number") from None
        if value <= 0 or value != value.to_integral_value():
            raise ParseError("should be a whole number above zero")
        return int(value)
    if field.kind == "money":
        return _money(raw)
    if field.kind == "date":
        return _date(raw)
    if field.kind == "bool":
        return _bool(raw)
    if field.kind == "choice":
        text = normalise_header(raw)
        for value, label in field.choices:
            if text in (normalise_header(value), normalise_header(label)):
                return value
        options = " or ".join(label for _, label in field.choices)
        raise ParseError(f"should be {options}")
    raise ValueError(f"Unknown field kind {field.kind}")


# Units: the rules beyond each cell


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_unit(values: dict, existing: dict | None) -> list[str]:
    """Problems with a unit once its new values are merged over what it already has, in plain
    words. `existing` is None for a new unit."""
    merged = {**(existing or {}), **{k: v for k, v in values.items() if v is not None}}
    problems = []
    if not merged.get("label"):
        problems.append("The unit number is missing.")
    if not merged.get("carpet_area_sqft"):
        problems.append("The carpet area is missing.")
    sold = bool(merged.get("buyer_name"))
    if sold and not merged.get("booked_on"):
        problems.append("A sold unit needs its booking date.")
    if sold and not merged.get("agreement_value"):
        problems.append("A sold unit needs its agreement value.")
    if not sold and (merged.get("agreement_value") or merged.get("booked_on")):
        problems.append("A unit with a booking date or agreement value needs its buyer.")
    email = merged.get("buyer_email")
    if email and not _EMAIL.match(email):
        problems.append("The buyer's email does not look right.")
    return problems
