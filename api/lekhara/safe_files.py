"""Opening uploaded files without letting one take the server down.

Excel (.xlsx) and Word files are zip archives. A small upload can be built to unpack to many
gigabytes (a decompression bomb) and exhaust the server's memory while it is read. Before any
such file is opened, its directory is read, which costs nothing, and a file that would unpack
far beyond any real spreadsheet is refused. XML inside them is read with defusedxml where
openpyxl uses it, and Python's own XML parser refuses runaway entity expansion.
"""

import io
import zipfile

from lekhara.services import ServiceError

MAX_UNPACKED = 500 * 1024 * 1024
"""More than any real spreadsheet unpacks to."""
MAX_RATIO = 100
"""Real spreadsheets compress about 5 to 20 times; bombs, thousands of times."""
MAX_ENTRIES = 10_000


def check_zip(data: bytes) -> None:
    """Refuses a zip-based file that would unpack to far more than it weighs. A file that is
    not a zip at all is left for its reader to refuse in its own words."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError):
        return
    entries = archive.infolist()
    unpacked = sum(e.file_size for e in entries)
    too_dense = unpacked > 20 * 1024 * 1024 and unpacked > MAX_RATIO * max(len(data), 1)
    if len(entries) > MAX_ENTRIES or unpacked > MAX_UNPACKED or too_dense:
        raise ServiceError(
            "This file unpacks to far more than a spreadsheet should, so it was not opened. "
            "Export it again from the program it came from."
        )
