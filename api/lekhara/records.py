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

SUPPLIER_NAMES = (
    "supplier name",
    "vendor",
    "vendor name",
    "party",
    "party name",
    "contractor",
    "contractor name",
    "name",
    "creditor",
    "sundry creditor",
)
COST_LINE_NAMES = ("cost head", "budget head", "head", "cost code", "account head", "budget line")

SUPPLIERS = RecordType(
    kind="suppliers",
    title="Suppliers",
    key="name",
    fields=(
        Field(
            "name",
            "Supplier",
            "text",
            required=True,
            aliases=SUPPLIER_NAMES,
            help="The supplier's name as on their bills. Each supplier appears once.",
            example="Bharat TMT Steel",
        ),
        Field(
            "gstin",
            "GSTIN",
            "text",
            aliases=("gst no", "gst number", "gstin/uin", "gst", "gstin no", "gst registration"),
            help="15 characters. Blank if the supplier is not registered for GST.",
            example="29ABCDE1234F1Z5",
        ),
        Field(
            "pan",
            "PAN",
            "text",
            aliases=("pan no", "pan number", "income tax pan"),
            help="Filled in from the GSTIN if left blank.",
            example="ABCDE1234F",
        ),
        Field(
            "state",
            "State",
            "text",
            aliases=("state name", "place of supply"),
            help="Filled in from the GSTIN if left blank.",
            example="Karnataka",
        ),
        Field(
            "msme_category",
            "MSME category",
            "choice",
            aliases=("msme", "msme type", "udyam category", "enterprise type", "msme status"),
            choices=(
                ("none", "Not MSME"),
                ("micro", "Micro"),
                ("small", "Small"),
                ("medium", "Medium"),
            ),
            help="From the supplier's Udyam certificate. Micro and small suppliers must be paid "
            "within 45 days.",
            example="Small",
        ),
        Field(
            "udyam_number",
            "Udyam number",
            "text",
            aliases=("udyam", "udyam registration", "udyam no", "msme registration no"),
            example="UDYAM-KR-03-0012345",
        ),
        Field(
            "written_agreement",
            "Written agreement on payment terms",
            "bool",
            aliases=("agreement", "written agreement", "payment terms agreed"),
            help="Yes if a written agreement fixes when you pay. Without one, bills from micro "
            "and small suppliers are due in 15 days.",
            example="Yes",
        ),
    ),
)

BILLS = RecordType(
    kind="bills",
    title="Suppliers' bills",
    key="bill_no",
    fields=(
        Field(
            "supplier",
            "Supplier",
            "text",
            required=True,
            aliases=SUPPLIER_NAMES + ("gstin of supplier", "supplier gstin"),
            help="The supplier's name or GSTIN. A supplier not yet in Lekhara is added.",
            example="Bharat TMT Steel",
        ),
        Field(
            "bill_no",
            "Bill number",
            "text",
            required=True,
            aliases=(
                "invoice no",
                "invoice number",
                "bill no",
                "supplier invoice no",
                "inv no",
                "ra bill no",
                "invoice",
                "bill",
            ),
            help="The supplier's own invoice or RA bill number.",
            example="BTS/2026/0412",
        ),
        Field(
            "bill_date",
            "Bill date",
            "date",
            required=True,
            aliases=("invoice date", "date", "inv date", "bill dt"),
            example="12/04/2026",
        ),
        Field(
            "taxable_value",
            "Taxable value",
            "money",
            required=True,
            aliases=(
                "taxable amount",
                "basic amount",
                "amount before tax",
                "value",
                "taxable",
                "basic value",
            ),
            help="Before GST, in rupees.",
            example="1850000",
        ),
        Field(
            "gst_amount",
            "GST",
            "money",
            aliases=("gst amount", "tax amount", "total tax", "tax", "igst cgst sgst"),
            help="CGST, SGST and IGST together.",
            example="333000",
        ),
        Field(
            "accepted_on",
            "Accepted on",
            "date",
            aliases=("date of acceptance", "received on", "goods received on", "grn date"),
            help="When the goods or work were accepted; the MSME clock starts here. The bill "
            "date if left blank.",
            example="15/04/2026",
        ),
        Field(
            "paid_on",
            "Paid on",
            "date",
            aliases=("payment date", "paid date", "date of payment", "paid"),
            help="Blank while unpaid.",
            example="20/05/2026",
        ),
        Field(
            "cost_line",
            "Cost line",
            "text",
            aliases=COST_LINE_NAMES,
            help="The cost line's code or name, so the bill counts as cost incurred, and as "
            "paid once paid. Leave blank when your cost comes from Tally.",
            example="CIV",
        ),
        Field(
            "is_cement",
            "Cement",
            "bool",
            aliases=("is cement", "cement purchase"),
            help="Yes for cement: from unregistered suppliers it carries reverse charge.",
            example="No",
        ),
        Field(
            "rcm_paid",
            "Reverse charge paid",
            "bool",
            aliases=("rcm", "rcm paid"),
            example="No",
        ),
        Field(
            "excluded",
            "Leave out of the 80% test",
            "bool",
            aliases=("excluded", "exclude", "not for 80"),
            help="Yes for bills the 80% test leaves out, such as electricity, fuel or capital "
            "goods.",
            example="No",
        ),
    ),
)

COMMITMENTS = RecordType(
    kind="commitments",
    title="Commitments",
    key="reference",
    fields=(
        Field(
            "reference",
            "Order number",
            "text",
            required=True,
            aliases=(
                "po no",
                "po number",
                "wo no",
                "work order no",
                "work order number",
                "purchase order no",
                "order no",
                "contract no",
                "reference",
                "po",
                "wo",
            ),
            help="The work order, purchase order or contract number. Each appears once.",
            example="WO/CIV/014",
        ),
        Field(
            "cost_line",
            "Cost line",
            "text",
            required=True,
            aliases=COST_LINE_NAMES,
            help="The cost line's code or name.",
            example="CIV",
        ),
        Field(
            "amount",
            "Amount",
            "money",
            required=True,
            aliases=("order value", "contract value", "po value", "wo value", "value"),
            help="What the order commits you to, before GST. Change it when a variation is agreed.",
            example="4.5 crore",
        ),
        Field(
            "committed_on",
            "Ordered on",
            "date",
            required=True,
            aliases=("po date", "wo date", "order date", "date", "contract date"),
            example="01/04/2026",
        ),
        Field(
            "supplier",
            "Supplier",
            "text",
            aliases=SUPPLIER_NAMES,
            example="Shree Constructions",
        ),
        Field(
            "description",
            "What for",
            "text",
            aliases=("description", "scope", "particulars", "work", "details", "nature of work"),
            example="Structure, towers A and B",
        ),
    ),
)

LANDOWNER_PAYMENTS = RecordType(
    kind="landowner_payments",
    title="Landowner payments",
    key="landowner",
    fields=(
        Field(
            "landowner",
            "Landowner",
            "text",
            required=True,
            aliases=("landowner name", "payee", "paid to", "name", "party", "party name"),
            help="The landowner's name or PAN, as in Lekhara.",
            example="R. Venkatesh",
        ),
        Field(
            "paid_on",
            "Paid on",
            "date",
            required=True,
            aliases=("date", "payment date", "date of payment", "paid date", "value date"),
            help="Day first, as in 05/06/2025.",
            example="05/06/2025",
        ),
        Field(
            "amount",
            "Amount",
            "money",
            required=True,
            aliases=("amount paid", "paid", "payment", "gross amount", "consideration"),
            help="The amount paid or credited to the landowner before TDS, in rupees. TDS goes "
            "in its own column.",
            example="3000000",
        ),
        Field(
            "tds_deducted",
            "TDS deducted",
            "money",
            aliases=("tds", "tds amount", "tds 194ic", "tds deducted u/s 194ic"),
            help="TDS cut under s.194-IC on consideration paid in money.",
            example="300000",
        ),
        Field(
            "deposit",
            "Refundable deposit",
            "bool",
            aliases=("deposit", "security deposit", "refundable", "is deposit"),
            help="Yes for a refundable security deposit, which carries no TDS; no for "
            "consideration. No if left blank.",
            example="No",
        ),
        Field(
            "reference",
            "Reference",
            "text",
            aliases=("utr", "utr no", "cheque no", "cheque number", "reference no", "note"),
            help="UTR, cheque number or a note.",
            example="HDFCN52025060598765",
        ),
    ),
)

APPROVALS = RecordType(
    kind="approvals",
    title="Approvals",
    key="name",
    fields=(
        Field(
            "name",
            "Approval",
            "text",
            required=True,
            aliases=("approval name", "clearance", "noc", "permission", "consent", "particulars"),
            help="What the approval is, such as Fire NOC or Environmental clearance. Each "
            "appears once.",
            example="Fire NOC (provisional)",
        ),
        Field(
            "authority",
            "Authority",
            "text",
            aliases=("issued by", "department", "issuing authority", "agency"),
            example="Karnataka State Fire and Emergency Services",
        ),
        Field(
            "reference",
            "Number",
            "text",
            aliases=(
                "reference",
                "approval no",
                "approval number",
                "order no",
                "file no",
                "ref no",
            ),
            example="KSFES/NOC/2024/1187",
        ),
        Field(
            "applied_on",
            "Applied on",
            "date",
            aliases=("application date", "date of application", "applied"),
            example="10/01/2024",
        ),
        Field(
            "granted_on",
            "Granted on",
            "date",
            aliases=("date of issue", "issued on", "approval date", "granted", "issue date"),
            example="22/03/2024",
        ),
        Field(
            "valid_until",
            "Valid until",
            "date",
            aliases=("expiry", "expiry date", "expires on", "valid till", "validity", "valid upto"),
            help="Blank if it does not lapse.",
            example="21/03/2026",
        ),
        Field(
            "note",
            "Note",
            "text",
            aliases=("remarks", "comments", "conditions", "status remarks"),
            example="Final NOC to be applied for before the occupancy certificate",
        ),
    ),
)

FILINGS = RecordType(
    kind="filings",
    title="K-RERA filings",
    key="period_end",
    fields=(
        Field(
            "kind",
            "Filing",
            "choice",
            required=True,
            aliases=("filing", "report", "type", "return"),
            choices=(
                ("qpr", "Quarterly progress report"),
                ("annual_audit", "Annual audit report"),
            ),
            example="Quarterly progress report",
        ),
        Field(
            "period_end",
            "Period ending",
            "date",
            required=True,
            aliases=("quarter ending", "quarter end", "year ending", "period", "for the period"),
            help="The last day of the quarter or financial year the filing covers.",
            example="30/06/2026",
        ),
        Field(
            "filed_on",
            "Filed on",
            "date",
            required=True,
            aliases=("date of filing", "filing date", "submitted on", "uploaded on"),
            example="12/07/2026",
        ),
        Field(
            "reference",
            "Acknowledgement",
            "text",
            aliases=("acknowledgement no", "reference", "ack no", "receipt no", "ref no"),
            example="KRERA/QPR/2026/0412",
        ),
    ),
)

RECORD_TYPES = {
    r.kind: r
    for r in (
        UNITS,
        RECEIPTS,
        SUPPLIERS,
        BILLS,
        COMMITMENTS,
        LANDOWNER_PAYMENTS,
        APPROVALS,
        FILINGS,
    )
}


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
