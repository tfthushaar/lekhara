"""Lekhara Connector for Tally.

Runs on the computer with Tally. Every few minutes it asks TallyPrime for its masters and recent
vouchers, over Tally's own XML interface on this computer, and sends them to Lekhara over HTTPS.
Nothing in Tally is changed, and nothing on this computer is opened to the internet: the connector
only makes outgoing connections, to Tally on this computer and to Lekhara.

    lekhara-connector link ABCD-EFGH --server https://your-lekhara-address
                                  link this computer to a project, with the code from the
                                  project's Import page in Lekhara
    lekhara-connector run         keep going (the usual way; start it with Windows)
    lekhara-connector once        one sync, for running from the Task Scheduler
    lekhara-connector status      what it last did
    lekhara-connector unlink      forget the link on this computer

Options: --tally (Tally's address, http://localhost:9000 by default) and --company (the Tally
company to read, when more than one is open).

Before the first run, turn on TallyPrime's HTTP server: Help, Settings, Connectivity, and set
TallyPrime to act as a server (or both) on port 9000. Tally must be open with the company
loaded for the connector to read it.

Only the Python standard library is used, so the connector can be packaged as a single Windows
program.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

VERSION = "1.0"
DEFAULT_TALLY = "http://localhost:9000"

MASTERS = """<ENVELOPE>
<HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
<BODY><EXPORTDATA><REQUESTDESC>
<REPORTNAME>List of Accounts</REPORTNAME>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<ACCOUNTTYPE>All Masters</ACCOUNTTYPE>{company}
</STATICVARIABLES>
</REQUESTDESC></EXPORTDATA></BODY>
</ENVELOPE>"""

DAY_BOOK = """<ENVELOPE>
<HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
<BODY><EXPORTDATA><REQUESTDESC>
<REPORTNAME>Day Book</REPORTNAME>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVFROMDATE>{start}</SVFROMDATE>
<SVTODATE>{end}</SVTODATE>{company}
</STATICVARIABLES>
</REQUESTDESC></EXPORTDATA></BODY>
</ENVELOPE>"""

Http = Callable[[str, str, bytes | None, dict], tuple[int, bytes]]


class TallyUnavailable(Exception):
    """Tally is not running, its HTTP server is off, or no company is open."""


class LekharaError(Exception):
    """Lekhara refused or could not be reached."""


def urllib_http(method: str, url: str, body: bytes | None, headers: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def home() -> Path:
    override = os.environ.get("LEKHARA_CONNECTOR_HOME")
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "Lekhara"
    return Path.home() / ".config" / "lekhara"


def financial_year_start(today: date) -> date:
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        out += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    for name, (filename, data) in files.items():
        out += (
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="{name}"; filename="{filename}"\r\n'
            "Content-Type: application/xml\r\n\r\n"
        ).encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


class Connector:
    def __init__(
        self,
        folder: Path | None = None,
        *,
        http: Http = urllib_http,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] = datetime.now,
        log: Callable[[str], None] = print,
    ) -> None:
        self.folder = folder or home()
        self.path = self.folder / "connector.json"
        self.http, self.today, self.now, self.log = http, today, now, log
        self.config = self._load()

    # Settings kept on this computer

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

    @property
    def linked(self) -> bool:
        return bool(self.config.get("key") and self.config.get("server"))

    # Talking to Lekhara

    def _lekhara(self, method: str, path: str, body: bytes | None = None, kind="application/json"):
        headers = {"User-Agent": f"LekharaConnector/{VERSION}", "Content-Type": kind}
        if self.config.get("key"):
            headers["X-Lekhara-Connector"] = self.config["key"]
        try:
            status, data = self.http(
                method, self.config["server"].rstrip("/") + path, body, headers
            )
        except (urllib.error.URLError, OSError) as exc:
            raise LekharaError(f"Lekhara could not be reached: {exc}") from None
        try:
            payload = json.loads(data or b"{}")
        except ValueError:
            payload = {}
        if status >= 400:
            raise LekharaError(payload.get("detail") or f"Lekhara answered {status}.")
        return payload

    def link(self, code: str, server: str, *, tally: str | None = None, company: str | None = None):
        self.config = {
            "server": server.rstrip("/"),
            "tally": tally or self.config.get("tally") or DEFAULT_TALLY,
            "company": company,
        }
        body = json.dumps({"code": code, "name": platform.node()}).encode()
        answer = self._lekhara("POST", "/connector/link", body)
        self.config.update(
            key=answer["key"],
            project=answer.get("project"),
            interval_seconds=answer.get("interval_seconds", 300),
            recent_days=answer.get("recent_days", 7),
            full_sync_hours=answer.get("full_sync_hours", 24),
        )
        self.save()
        self.log(f"Linked to {answer.get('project')}. Run 'lekhara-connector run' to start.")
        return answer

    def unlink(self) -> None:
        self.config = {}
        if self.path.exists():
            self.path.unlink()
        self.log("This computer is no longer linked. Unlink it in Lekhara too.")

    def heartbeat(self, state: str | None) -> None:
        body = json.dumps({"state": state, "company": self.config.get("company")}).encode()
        try:
            self._lekhara("POST", "/connector/heartbeat", body)
        except LekharaError as exc:
            self.log(str(exc))

    # Talking to Tally

    def _company(self) -> str:
        company = self.config.get("company")
        return f"\n<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>" if company else ""

    def tally(self, request: str) -> bytes:
        url = self.config.get("tally") or DEFAULT_TALLY
        headers = {"Content-Type": "text/xml; charset=utf-8"}
        try:
            status, data = self.http("POST", url, request.encode("utf-8"), headers)
        except (urllib.error.URLError, OSError):
            raise TallyUnavailable(
                f"Tally did not answer at {url}: is TallyPrime open, with its HTTP server on?"
            ) from None
        if status >= 400:
            raise TallyUnavailable(f"Tally answered {status}.")
        head = data[:4000].decode("utf-8", "ignore").replace("\x00", "")
        if "<LINEERROR>" in head:
            message = head.split("<LINEERROR>", 1)[1].split("</LINEERROR>", 1)[0].strip()
            raise TallyUnavailable(f"Tally said: {message or 'no company is open'}")
        return data

    # One sync

    def _due(self, key: str, hours: float) -> bool:
        last = self.config.get(key)
        if not last:
            return True
        return self.now() - datetime.fromisoformat(last) >= timedelta(hours=hours)

    def sync_once(self) -> str:
        if not self.linked:
            raise LekharaError("Link this computer first: lekhara-connector link CODE --server URL")
        try:
            masters = None
            if self._due("masters_at", self.config.get("full_sync_hours", 24)):
                masters = self.tally(MASTERS.format(company=self._company()))
            full = self._due("full_at", self.config.get("full_sync_hours", 24))
            today = self.today()
            start = (
                financial_year_start(today)
                if full
                else today - timedelta(days=self.config.get("recent_days", 7))
            )
            vouchers = self.tally(
                DAY_BOOK.format(
                    start=start.strftime("%Y%m%d"),
                    end=today.strftime("%Y%m%d"),
                    company=self._company(),
                )
            )
        except TallyUnavailable as exc:
            self.heartbeat(str(exc))
            self.log(str(exc))
            return str(exc)

        digest = hashlib.sha256(vouchers).hexdigest()
        if not masters and digest == self.config.get("last_digest"):
            self.heartbeat(None)
            message = "No change in Tally since the last sync."
            self.log(message)
            return message
        files = {"vouchers": ("daybook.xml", vouchers)}
        if masters:
            files["masters"] = ("masters.xml", masters)
        body, kind = multipart({"company": self.config.get("company") or ""}, files)
        answer = self._lekhara("POST", "/connector/tally", body, kind)
        stamp = self.now().isoformat(timespec="seconds")
        if masters:
            self.config["masters_at"] = stamp
        if full:
            self.config["full_at"] = stamp
        self.config["last_digest"] = digest
        self.config["last_sync_at"] = stamp
        self.config["last_message"] = answer.get("message") or answer.get("status")
        self.save()
        message = answer.get("message") or (
            "No change." if answer.get("status") == "unchanged" else "Sent."
        )
        self.log(message)
        return message

    def run_forever(self) -> None:
        self.log(f"Lekhara Connector {VERSION}: sending Tally to {self.config.get('project')}.")
        while True:
            try:
                self.sync_once()
            except LekharaError as exc:
                self.log(str(exc))
                if "unlinked" in str(exc):
                    return
            time.sleep(max(60, int(self.config.get("interval_seconds", 300))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lekhara-connector", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    link = sub.add_parser("link", help="link this computer to a project")
    link.add_argument("code")
    link.add_argument("--server", required=True)
    link.add_argument("--tally", default=None)
    link.add_argument("--company", default=None)
    for name in ("run", "once", "status", "unlink"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    connector = Connector()
    try:
        if args.command == "link":
            connector.link(args.code, args.server, tally=args.tally, company=args.company)
        elif args.command == "run":
            connector.run_forever()
        elif args.command == "once":
            connector.sync_once()
        elif args.command == "status":
            c = connector.config
            print(
                f"Linked to {c.get('project')} at {c.get('server')}; last sync "
                f"{c.get('last_sync_at') or 'never'}: {c.get('last_message') or ''}"
                if connector.linked
                else "Not linked."
            )
        elif args.command == "unlink":
            connector.unlink()
    except LekharaError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
