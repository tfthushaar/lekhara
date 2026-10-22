"""Watermarking PDFs opened from a data room with who opened them, and when.

A lender or investor can save or forward a document once it is on their screen; nothing a web
page does can stop that. A watermark makes it traceable instead: every page carries, faintly
across it, the visitor's email and the date, and along the foot the whole of it. The idea comes
from Papermark's per-viewer watermarks.

The mark is added to each page as a separate layer in the standard Helvetica font, partly
transparent, over the page's own content, so the document underneath is unchanged and still
searchable. Only PDFs are marked; a photo is served as it is.
"""

import math
from datetime import date
from io import BytesIO

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
)


def _pdf_text(text: str) -> str:
    """Text as a PDF string in Helvetica's WinAnsi encoding: brackets and backslashes escaped,
    anything the font cannot show replaced."""
    safe = text.encode("cp1252", errors="replace").decode("cp1252")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _resources() -> DictionaryObject:
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    faint = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/ca"): FloatObject(0.16),
            NameObject("/CA"): FloatObject(0.16),
        }
    )
    clear = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/ca"): FloatObject(0.75),
            NameObject("/CA"): FloatObject(0.75),
        }
    )
    return DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/LkF"): font}),
            NameObject("/ExtGState"): DictionaryObject(
                {NameObject("/LkFaint"): faint, NameObject("/LkFoot"): clear}
            ),
        }
    )


def room_marks(
    *,
    room: str,
    organization: str,
    on: date,
    visitor_name: str | None = None,
    visitor_email: str | None = None,
    audience: str | None = None,
) -> tuple[str, str]:
    """The mark across each page and the line along its foot, for a document opened from a data
    room: the visitor's email if the room asked who they are, or else who it was shared with."""
    day = f"{on.day} {on:%b %Y}"
    where = f'{organization}\'s data room "{room}"'
    if visitor_email:
        mark = f"{visitor_email}, {day}"
        footer = f"Opened by {visitor_name} ({visitor_email}) on {day}, from {where}."
    else:
        mark = f"{audience or room}, {day}"
        shared = f", shared with {audience}" if audience else ""
        footer = f"Opened on {day} from {where}{shared}."
    return mark, f"{footer} Confidential."


def _overlay(
    width: float, height: float, x0: float, y0: float, mark: str, footer: str
) -> PageObject:
    diagonal = math.hypot(width, height)
    # Helvetica averages about half the font size per character: fit the mark in 70% of the
    # diagonal, and no larger than a heading.
    size = max(8.0, min(min(width, height) / 22, 0.7 * diagonal / (0.5 * max(len(mark), 1))))
    angle = math.atan2(height, width)
    cos, sin = math.cos(angle), math.sin(angle)
    half = 0.5 * size * 0.5 * len(mark)
    commands = ["q /LkFaint gs 0 g BT", f"/LkF {size:.1f} Tf"]
    # One copy centred on each of three parallel diagonals, so cropping a corner leaves others.
    for k in (-1, 0, 1):
        cx = x0 + width / 2 - k * 0.28 * min(width, height) * sin
        cy = y0 + height / 2 + k * 0.28 * min(width, height) * cos
        x, y = cx - half * cos, cy - half * sin
        commands.append(f"{cos:.4f} {sin:.4f} {-sin:.4f} {cos:.4f} {x:.1f} {y:.1f} Tm")
        commands.append(f"({_pdf_text(mark)}) Tj")
    commands.append("ET Q")
    # As large as 9 points, smaller if that is what keeps the line on the page.
    foot = max(5.0, min(9.0, (width - 36) / (0.5 * max(len(footer), 1))))
    commands += [
        "q /LkFoot gs 0.25 g BT",
        f"/LkF {foot:.1f} Tf",
        f"1 0 0 1 {x0 + 18:.1f} {y0 + 10:.1f} Tm",
        f"({_pdf_text(footer)}) Tj",
        "ET Q",
    ]
    page = PageObject.create_blank_page(width=width, height=height)
    page[NameObject("/Resources")] = _resources()
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("latin-1"))
    page[NameObject("/Contents")] = stream
    return page


def watermark_pdf(data: bytes, mark: str, footer: str) -> bytes | None:
    """The PDF with every page marked, or None if it cannot be (a locked or damaged PDF), so the
    caller can decide what to serve instead."""
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            return None
        writer = PdfWriter(clone_from=reader)
        for page in writer.pages:
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            overlay = _overlay(width, height, float(box.left), float(box.bottom), mark, footer)
            page.merge_page(overlay, over=True)
        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:  # pypdf raises many different errors on damaged files
        return None
