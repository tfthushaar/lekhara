"""Recognising a Tally export and reading it into a tree, or into rows for a report.

XML and JSON exports become the same tree of nodes, so one reader of ledgers and vouchers
serves both. Reports exported to Excel or text (the Day Book, Ledger Vouchers, Trial Balance,
lists of ledgers) become rows.
"""

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from lekhara.imports import read_rows
from lekhara.services import ServiceError

OBJECTS = {
    "voucher",
    "ledger",
    "group",
    "costcentre",
    "costcategory",
    "stockitem",
    "stockgroup",
    "unit",
    "godown",
    "vouchertype",
    "currency",
}
_META = {"svcurrentcompany", "remotecmpname", "svfromdate", "svtodate", "companyname"}

HOW_TO_EXPORT = (
    "In TallyPrime, open the company, press Alt+E (Export) and choose Masters (All Masters) and "
    "then Transactions (All Vouchers for the period), with the file format set to XML. "
    "An Excel export of the Day Book also works, with less detail."
)


@dataclass
class Node:
    """One element of a Tally export. Names are lowercase; a list keeps its '.list' suffix."""

    name: str
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)

    def _match(self, child: "Node", names: tuple[str, ...]) -> bool:
        return child.name in names or child.name.removesuffix(".list") in names

    def first(self, *names: str) -> "Node | None":
        return next((c for c in self.children if self._match(c, names)), None)

    def all(self, *names: str) -> list["Node"]:
        return [c for c in self.children if self._match(c, names)]

    def get(self, *names: str) -> str:
        """The text of the first child with any of these names, or the attribute of that name."""
        for name in names:
            child = self.first(name)
            if child is not None and child.text:
                return child.text
            if self.attrs.get(name):
                return self.attrs[name]
        return ""

    def texts(self, *names: str) -> list[str]:
        """Texts of a list like ADDRESS.LIST, whichever way the export nests it."""
        out = []
        for child in self.all(*names):
            if child.text:
                out.append(child.text)
            out.extend(c.text for c in child.children if c.text)
        return out

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


# Recognising the file


def decode(data: bytes) -> str:
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    head = data[:400]
    if head.count(b"\x00") > len(head) // 4:
        encoding = "utf-16-le" if head[1:2] == b"\x00" else "utf-16-be"
        return data.decode(encoding, errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def detect(filename: str, data: bytes) -> str:
    """xml, json, xlsx, text, or an unreadable kind: pdf, image, html, xls."""
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith((b"\xff\xd8\xff", b"\x89PNG")):
        return "image"
    if data.startswith(b"PK\x03\x04"):
        return "xlsx"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    head = decode(data[:8000]).lstrip("﻿ \t\r\n")
    lowered = head[:3000].casefold()
    if head.startswith("<"):
        return "html" if "<html" in lowered or "<!doctype html" in lowered else "xml"
    if head.startswith(("{", "[")):
        return "json"
    return "text"


UNREADABLE = {
    "pdf": "This is a PDF, which is made for printing, not for reading as data.",
    "image": "This is a picture of a report, not the data itself.",
    "html": "This is a web page export, which loses the structure of the data.",
    "xls": "This is an old-style Excel file (.xls). Save it as .xlsx, or export again from Tally.",
}


# XML


_BAD_REF = re.compile(r"&#(x[0-9a-fA-F]+|\d+);")
_BAD_CHAR = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean_xml(text: str) -> str:
    """Removes what Tally writes but XML forbids: control characters such as the &#4; it puts
    before reserved group names, and an encoding declaration that no longer applies."""

    def ref(m: re.Match) -> str:
        raw = m.group(1)
        code = int(raw[1:], 16) if raw[0] in "xX" else int(raw)
        return "" if code < 32 and code not in (9, 10, 13) else m.group(0)

    text = _BAD_REF.sub(ref, text)
    text = _BAD_CHAR.sub("", text)
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("﻿"))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _node(element: ET.Element) -> Node:
    return Node(
        name=_local(element.tag),
        text=(element.text or "").strip(),
        attrs={_local(k): v.strip() for k, v in element.attrib.items()},
        children=[_node(child) for child in element],
    )


def read_xml(text: str) -> tuple[list[Node], dict[str, str]]:
    text = _clean_xml(text)
    if re.search(r"<!(DOCTYPE|ENTITY)", text[:5000], re.IGNORECASE):
        raise ServiceError("This XML file declares its own entities, which Lekhara does not read.")
    parser = ET.XMLPullParser(events=("start", "end"))
    objects: list[Node] = []
    meta: dict[str, str] = {}
    depth_in_object = 0
    try:
        for start in range(0, len(text), 1 << 20):
            parser.feed(text[start : start + (1 << 20)])
            for event, element in parser.read_events():
                name = _local(element.tag)
                if event == "start":
                    if name in OBJECTS:
                        depth_in_object += 1
                    continue
                if name in _META and element.text and name not in meta:
                    meta[name] = element.text.strip()
                if name in OBJECTS:
                    depth_in_object -= 1
                    if depth_in_object == 0:
                        objects.append(_node(element))
                        element.clear()
        parser.close()
    except ET.ParseError as exc:
        raise ServiceError(
            f"This XML file could not be read ({exc}). Export it again from Tally; if it was "
            "edited by hand, the edit may have broken it."
        ) from None
    return objects, meta


# JSON (TallyPrime 7.0 and later)


def _json_node(name: str, value) -> list[Node]:
    name = name.casefold()
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_json_node(name, item))
        return out
    if isinstance(value, dict):
        node = Node(name=name)
        for key, inner in value.items():
            if key.casefold() in ("@attributes", "attributes"):
                node.attrs.update({k.casefold(): str(v) for k, v in (inner or {}).items()})
            else:
                node.children.extend(_json_node(key, inner))
        return [node]
    return [Node(name=name, text="" if value is None else str(value).strip())]


def _object_of(item: Node) -> Node | None:
    """A tallymessage entry is either wrapped in its type ({"voucher": {...}}), labelled by a
    metadata block, or bare; work out which."""
    if len(item.children) == 1 and item.children[0].name in OBJECTS:
        return item.children[0]
    meta = item.first("metadata")
    if meta is not None:
        kind = meta.get("type", "objecttype").casefold().replace(" ", "")
        if kind in OBJECTS:
            item.name = kind
            for key in ("name",):
                if meta.get(key) and not item.get(key):
                    item.attrs[key] = meta.get(key)
            return item
    keys = {c.name.removesuffix(".list") for c in item.children}
    if "vouchertypename" in keys or "allledgerentries" in keys or "ledgerentries" in keys:
        item.name = "voucher"
        return item
    if {"name", "parent"} <= keys or "parent" in keys:
        item.name = "ledger"
        return item
    return None


def read_json(text: str) -> tuple[list[Node], dict[str, str]]:
    try:
        data = json.loads(text.lstrip("﻿"))
    except json.JSONDecodeError as exc:
        raise ServiceError(
            f"This JSON file could not be read ({exc.msg}). Export it again."
        ) from None
    messages: list = []
    meta: dict[str, str] = {}

    def find(value) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                lowered = key.casefold()
                if lowered == "tallymessage":
                    messages.extend(inner if isinstance(inner, list) else [inner])
                elif lowered in _META and isinstance(inner, str | int):
                    meta.setdefault(lowered, str(inner))
                else:
                    find(inner)
        elif isinstance(value, list):
            for inner in value:
                find(inner)

    find(data)
    objects = []
    for raw in messages:
        for item in _json_node("item", raw):
            obj = _object_of(item)
            if obj is not None:
                objects.append(obj)
    return objects, meta


# Reports: Excel, CSV or ASCII text


def read_table(filename: str, data: bytes, kind: str) -> list[list]:
    if kind == "xlsx":
        return read_rows("report.xlsx", data)
    text = decode(data)
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]
    return [row for row in rows if any(cell for cell in row)]
