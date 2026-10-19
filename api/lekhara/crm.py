"""Exports from the CRMs builders use, read as they come out of the CRM.

Most of the work is in the column names, which the record types list as aliases (Sell.Do's
"Primary Lead Name", LeadSquared's "mx_Unit_Number", Zoho's "Deal Name" and so on). Here, the
few things names alone cannot do:

- recognise which CRM a file came from, to say so on the preview;
- join a first and a last name into the buyer's name, as LeadSquared and Salesforce split them;
- treat a unit or deal whose status is not booked (available, blocked, on hold, lost) as unsold,
  so a buyer's name on a held unit does not make it a sale.

Built from the CRMs' published field names; to be checked against real exports from design
partners, and extended as they bring others.
"""

from lekhara.records import normalise_header

SOURCES = (
    (
        "Sell.Do",
        {"sell do lead id", "primary lead name", "booking id", "unit name", "tower name",
         "lead id", "project name", "primary phone", "primary email", "booking amount"},
    ),
    (
        "LeadSquared",
        {"prospect id", "emailaddress", "mx unit number", "mx tower", "opportunity name",
         "lead stage", "first name", "last name", "lead owner"},
    ),
    (
        "Zoho CRM",
        {"deal name", "account name", "contact name", "closing date", "deal owner", "stage",
         "record id"},
    ),
    (
        "Salesforce",
        {"opportunity name", "account name", "close date", "opportunity owner", "stage",
         "opportunity id"},
    ),
    (
        "HubSpot",
        {"deal name", "deal stage", "close date", "associated contact", "deal owner",
         "record id"},
    ),
)  # fmt: skip

STATUS_COLUMNS = {"status", "unit status", "inventory status", "booking status", "stage",
                  "deal stage", "lead stage", "opportunity stage"}  # fmt: skip
BOOKED = ("booked", "sold", "registered", "agreement", "allotted", "closed won", "won",
          "booking confirmed", "possession")  # fmt: skip
BUYER_FIELDS = ("buyer_name", "buyer_phone", "buyer_email", "booked_on", "agreement_value")


def recognise(headers: list[str]) -> str | None:
    names = {normalise_header(h) for h in headers}
    best, hits = None, 1
    for label, signature in SOURCES:
        found = len(names & signature)
        if found > hits:
            best, hits = label, found
    return best


def _booked(status: str) -> bool:
    text = normalise_header(status)
    if any(word in text for word in ("not booked", "unsold", "cancel", "lost")):
        return False
    return any(word in text for word in BOOKED)


def prepare(kind: str, headers: list[str], body: list[list]) -> tuple[list[str], list[list]]:
    """The headers and rows with first and last names joined and, for units, the buyer's
    details left out of any row whose status says it is not booked."""
    names = [normalise_header(h) for h in headers]
    if kind == "units" and "first name" in names and "last name" in names:
        has_buyer = any(
            n in names
            for n in ("buyer", "buyer name", "customer name", "primary lead name", "lead name")
        )
        if not has_buyer:
            first, last = names.index("first name"), names.index("last name")
            headers = [*headers, "Buyer"]
            body = [
                [
                    *row,
                    " ".join(str(row[i]).strip() for i in (first, last) if i < len(row) and row[i]),
                ]
                for row in body
            ]
            names.append("buyer")
    status = next((i for i, n in enumerate(names) if n in STATUS_COLUMNS), None)
    if kind == "units" and status is not None:
        from lekhara.records import UNITS, match_columns

        mapping = match_columns(UNITS, headers)
        buyer_columns = [i for i, key in mapping.items() if key in BUYER_FIELDS]
        cleaned = []
        for row in body:
            value = row[status] if status < len(row) else ""
            if value not in ("", None) and not _booked(str(value)):
                row = ["" if i in buyer_columns else v for i, v in enumerate(row)]
            cleaned.append(row)
        body = cleaned
    return headers, body
