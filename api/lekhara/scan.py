"""Checking files for viruses before Lekhara keeps them, with ClamAV.

When `LEKHARA_CLAMAV_URL` is set (tcp://host:3310), every file uploaded, emailed in or sent by
the Tally connector is streamed to the clamd daemon first (its INSTREAM command). A file found
to carry a virus is refused with its name. If the scanner cannot be reached, files are refused
too, rather than let through unchecked. Without the setting, as in local development, nothing
is scanned.
"""

import socket
import struct
from urllib.parse import urlparse

from lekhara.config import Settings
from lekhara.services import ServiceError

CHUNK = 64 * 1024
TIMEOUT_SECONDS = 30


class Infected(ServiceError):
    def __init__(self, filename: str, signature: str) -> None:
        super().__init__(
            f"{filename} carries a virus ({signature}), so it was not accepted. Delete it, and "
            "ask whoever sent it for a clean copy.",
            400,
        )
        self.signature = signature


def check(settings: Settings, data: bytes, filename: str = "The file") -> None:
    """Returns when the file is clean or no scanner is set up; raises otherwise."""
    if not settings.clamav_url:
        return
    url = urlparse(settings.clamav_url)
    try:
        with socket.create_connection(
            (url.hostname or "localhost", url.port or 3310), timeout=TIMEOUT_SECONDS
        ) as conn:
            conn.sendall(b"zINSTREAM\0")
            for start in range(0, len(data), CHUNK):
                chunk = data[start : start + CHUNK]
                conn.sendall(struct.pack(">I", len(chunk)) + chunk)
            conn.sendall(struct.pack(">I", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = conn.recv(4096)
                if not part:
                    break
                reply += part
    except OSError:
        raise ServiceError(
            "Files cannot be checked for viruses just now, so this one was not accepted. Try "
            "again in a few minutes.",
            503,
        ) from None
    text = reply.rstrip(b"\0").decode(errors="replace").strip()
    if text.endswith("FOUND"):
        signature = text.removeprefix("stream:").removesuffix("FOUND").strip()
        raise Infected(filename, signature or "a known virus")
    if not text.endswith("OK"):
        raise ServiceError(
            "The virus check did not finish, so this file was not accepted. Try again.", 503
        )
