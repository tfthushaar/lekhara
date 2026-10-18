"""File storage for the document vault.

Files are addressed by the SHA-256 of their contents, so the same file uploaded twice
is stored once and a stored file can never change under its key. Local disk today;
an S3-compatible store in production implements the same two methods.
"""

import contextlib
import hashlib
import os
import re
from pathlib import Path
from typing import Protocol

_KEY = re.compile(r"^[0-9a-f]{64}$")


class Storage(Protocol):
    def put(self, data: bytes) -> str: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError("Not a storage key")
        return self.root / key[:2] / key

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".partial")
            partial.write_bytes(data)
            os.replace(partial, path)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        """Remove a file no record uses any more."""
        with contextlib.suppress(FileNotFoundError, ValueError):
            self._path(key).unlink()
