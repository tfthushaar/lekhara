"""Reading text out of PDFs, and writing plain ones.

Text is read page by page so that a search result can say which page it came from.
The writer makes simple text-only A4 pages in Helvetica: enough for demo documents
and for packs Lekhara prepares. It handles Latin-1 text only.
"""

import textwrap
from io import BytesIO

from pypdf import PdfReader

_PAGE_WIDTH, _PAGE_HEIGHT = 595, 842
_LINE_HEIGHT = 14
_LINES_PER_PAGE = 52
_WRAP_AT = 92


def read_pages(data: bytes) -> list[str] | None:
    """The text of each page, or None when the file cannot be read as a PDF."""
    try:
        reader = PdfReader(BytesIO(data))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception:  # pypdf raises many different errors on damaged files
        return None


def _escape(line: str) -> str:
    line = line.replace("₹", "Rs. ")
    line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return line.encode("latin-1", "replace").decode("latin-1")


def _layout(pages: list[list[str]], wrap_at: int = _WRAP_AT) -> list[list[str]]:
    """Wraps long lines and spills over onto new pages."""
    out = []
    for lines in pages:
        wrapped = []
        for line in lines:
            wrapped.extend(textwrap.wrap(line, wrap_at) or [""])
        for start in range(0, max(len(wrapped), 1), _LINES_PER_PAGE):
            out.append(wrapped[start : start + _LINES_PER_PAGE])
    return out


def write_pdf(
    pages: list[list[str]], *, title: str = "", font_size: int = 11, wrap_at: int = _WRAP_AT
) -> bytes:
    """Text pages; a smaller font with a wider wrap fits wide tables such as statements."""
    pages = _layout(pages, wrap_at)
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    kids = []
    for i, lines in enumerate(pages):
        page_id, content_id = 5 + 2 * i, 6 + 2 * i
        kids.append(f"{page_id} 0 R")
        ops = ["BT", f"/F1 {font_size} Tf", f"{font_size + 3} TL", f"36 {_PAGE_HEIGHT - 48} Td"]
        ops += [f"({_escape(line)}) Tj T*" for line in lines]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    objects[4] = f"<< /Title ({_escape(title)}) /Producer (Lekhara) >>".encode("latin-1")

    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = out.tell()
        out.write(f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n")
    xref = out.tell()
    size = max(objects) + 1
    out.write(f"xref\n0 {size}\n0000000000 65535 f \n".encode())
    for number in range(1, size):
        out.write(f"{offsets[number]:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {size} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()
