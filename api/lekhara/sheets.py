"""Writing cells into Excel and CSV files that people open on their own computers.

Excel takes text starting with = as a formula, and when it opens a CSV file, text starting with
+, - or @ as well. Lekhara writes text that came from outside (a CRM export, a bank narration,
an email) back out in its exports and templates, so that text must stay text, or a buyer named
=HYPERLINK(...) becomes a working link in the CFO's spreadsheet. In Excel files it is stored as
text explicitly; in CSV files, which carry no types, it gets a leading apostrophe, as OWASP
advises, and the Import centre takes the apostrophe off again.
"""

import re

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[+-]?\d[\d,]*(\.\d+)?")


def as_text(cell):
    """An openpyxl cell whose text value starts with = is kept as text, not a formula."""
    if isinstance(cell.value, str) and cell.value.startswith("="):
        cell.data_type = "s"
    return cell


def append(sheet, values: list) -> None:
    """sheet.append, with text kept as text."""
    sheet.append(values)
    for cell in sheet[sheet.max_row]:
        as_text(cell)


def csv_value(value):
    """A value for a CSV cell: text Excel would run is escaped; plain numbers are left alone."""
    if isinstance(value, str) and value.startswith(FORMULA_START) and not _NUMBER.fullmatch(value):
        return "'" + value
    return value


def from_csv(value: str) -> str:
    """Undoes csv_value when the file comes back in."""
    if value.startswith("'") and value[1:].startswith(FORMULA_START):
        return value[1:]
    return value
