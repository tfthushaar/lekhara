"""Backups: the database and every stored file, in one encrypted file.

    python -m lekhara.backup create <folder>            writes lekhara-backup-<time>.lkb there
    python -m lekhara.backup check <file>               opens it and checks everything in it
    python -m lekhara.backup restore <file> <folder>    unpacks it into a new, empty folder

The file is encrypted with LEKHARA_BACKUP_KEY, a passphrase kept apart from the servers and from
the backups themselves. It is AES-256-GCM in pieces of a megabyte, each sealed together with
its place and whether it is the last, so a backup cut short, or with pieces swapped or altered,
is refused rather than half restored.

`check` changes nothing: it opens every piece, unpacks into a temporary folder, checks each
stored document against the SHA-256 it is named by, and checks the database (SQLite's own
integrity check and a count of firms, or pg_restore's listing of a Postgres dump).

In production the hosting's point-in-time recovery for Postgres comes first; these files are
the copy kept elsewhere. Make one every day, keep the copies in storage that cannot delete
them for a set time (S3 Object Lock or the like), and test a restore every quarter.
"""

import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import struct
import subprocess
import sys
import tarfile
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from lekhara.config import Settings

MAGIC = b"LEKHARA-BACKUP-1\n"
PIECE = 1 << 20


class BackupError(Exception):
    pass


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _passphrase(settings: Settings) -> str:
    if not settings.backup_key or len(settings.backup_key) < 16:
        raise BackupError("Set LEKHARA_BACKUP_KEY to a passphrase of at least 16 characters.")
    return settings.backup_key


# Encrypting a stream in sealed pieces


def encrypt_file(source: Path, target: Path, passphrase: str) -> None:
    salt, prefix = secrets.token_bytes(16), secrets.token_bytes(8)
    aead = AESGCM(_key(passphrase, salt))
    size = source.stat().st_size
    with source.open("rb") as src, target.open("wb") as out:
        out.write(MAGIC + salt + prefix)
        index, sent = 0, 0
        while True:
            piece = src.read(PIECE)
            sent += len(piece)
            last = sent >= size
            sealed = aead.encrypt(
                prefix + struct.pack(">I", index), piece, MAGIC + struct.pack(">IB", index, last)
            )
            out.write(struct.pack(">IB", len(sealed), last) + sealed)
            index += 1
            if last:
                break


def decrypt_file(source: Path, target: Path, passphrase: str) -> None:
    with source.open("rb") as src, target.open("wb") as out:
        if src.read(len(MAGIC)) != MAGIC:
            raise BackupError("This is not a Lekhara backup.")
        salt, prefix = src.read(16), src.read(8)
        aead = AESGCM(_key(passphrase, salt))
        index = 0
        while True:
            head = src.read(5)
            if len(head) < 5:
                raise BackupError("The backup is cut short: its last piece is missing.")
            length, last = struct.unpack(">IB", head)
            sealed = src.read(length)
            try:
                piece = aead.decrypt(
                    prefix + struct.pack(">I", index),
                    sealed,
                    MAGIC + struct.pack(">IB", index, last),
                )
            except Exception:
                raise BackupError(
                    f"Piece {index + 1} does not open: the key is wrong, or the file was altered."
                ) from None
            out.write(piece)
            index += 1
            if last:
                if src.read(1):
                    raise BackupError("There is more after the last piece: the file was altered.")
                return


# Making one


def _database_into(settings: Settings, folder: Path) -> str:
    url = settings.database_url
    if url.startswith("sqlite"):
        path = url.split("///", 1)[1] if "///" in url else ""
        if not path or path == ":memory:":
            raise BackupError("An in-memory database cannot be backed up.")
        target = folder / "lekhara.sqlite"
        # A consistent copy, even while the API runs. (A connection's "with" commits but does
        # not close it, so each is closed explicitly.)
        with closing(sqlite3.connect(path)) as live, closing(sqlite3.connect(target)) as copy:
            live.backup(copy)
        return "sqlite"
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql"))
    target = folder / "lekhara.dump"
    env = {**os.environ, "PGPASSWORD": parsed.password or ""}
    command = ["pg_dump", "--format=custom", "--no-owner", f"--file={target}",
               f"--host={parsed.hostname}", f"--port={parsed.port or 5432}",
               f"--username={parsed.username}", parsed.path.lstrip("/")]  # fmt: skip
    try:
        subprocess.run(command, check=True, env=env, capture_output=True)  # nosec B603
    except FileNotFoundError:
        raise BackupError("pg_dump is not installed on this machine.") from None
    except subprocess.CalledProcessError as exc:
        raise BackupError(f"pg_dump failed: {exc.stderr.decode(errors='replace')[:300]}") from None
    return "postgres"


def create(settings: Settings, folder: Path) -> Path:
    passphrase = _passphrase(settings)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = folder / f"lekhara-backup-{stamp}.lkb"
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        kind = _database_into(settings, work)
        files = Path(settings.storage_dir)
        stored = [p for p in files.rglob("*") if p.is_file() and len(p.name) == 64]
        manifest = {
            "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "database": kind,
            "files": len(stored),
        }
        archive = work / "backup.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for path in work.iterdir():
                if path.name.startswith("lekhara."):
                    tar.add(path, arcname=f"database/{path.name}")
            for path in stored:
                tar.add(path, arcname=f"files/{path.parent.name}/{path.name}")
            data = json.dumps(manifest, indent=2).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        encrypt_file(archive, target, passphrase)
    return target


# Checking and restoring one


def _unpack(settings: Settings, backup: Path, folder: Path) -> dict:
    archive = folder / "backup.tar.gz"
    decrypt_file(backup, archive, _passphrase(settings))
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(folder, filter="data")  # refuses paths outside the folder
    archive.unlink()
    return json.loads((folder / "manifest.json").read_text())


def _verify(folder: Path, manifest: dict) -> list[str]:
    problems = []
    stored = (
        [p for p in (folder / "files").rglob("*") if p.is_file()]
        if (folder / "files").exists()
        else []
    )
    if len(stored) != manifest["files"]:
        problems.append(f"{manifest['files']} files were backed up but {len(stored)} came back.")
    for path in stored:
        if hashlib.sha256(path.read_bytes()).hexdigest() != path.name:
            problems.append(f"The file {path.name} does not match its fingerprint.")
    if manifest["database"] == "sqlite":
        with closing(sqlite3.connect(folder / "database" / "lekhara.sqlite")) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                problems.append("The database copy fails SQLite's integrity check.")
            manifest["firms"] = db.execute("SELECT count(*) FROM organizations").fetchone()[0]
    else:
        try:
            listing = subprocess.run(  # nosec B603 B607
                ["pg_restore", "--list", str(folder / "database" / "lekhara.dump")],
                check=True, capture_output=True,
            )  # fmt: skip
            manifest["database_entries"] = listing.stdout.count(b"\n")
        except FileNotFoundError:
            manifest["database_note"] = (
                "pg_restore is not installed here, so the dump was not listed."
            )
        except subprocess.CalledProcessError:
            problems.append("pg_restore cannot read the database dump.")
    return problems


def check(settings: Settings, backup: Path) -> dict:
    with tempfile.TemporaryDirectory() as work:
        manifest = _unpack(settings, backup, Path(work))
        problems = _verify(Path(work), manifest)
    return {**manifest, "problems": problems}


def restore(settings: Settings, backup: Path, folder: Path) -> dict:
    """Unpacks into a new folder: the database copy under database/, documents under files/.
    The running servers are not touched; swap the copies in while they are stopped."""
    if folder.exists() and any(folder.iterdir()):
        raise BackupError("Restore into a new, empty folder.")
    folder.mkdir(parents=True, exist_ok=True)
    manifest = _unpack(settings, backup, folder)
    problems = _verify(folder, manifest)
    if problems:
        shutil.rmtree(folder / "files", ignore_errors=True)
    return {**manifest, "problems": problems}


def main(argv: list[str]) -> int:
    from lekhara.config import get_settings

    settings = get_settings()
    try:
        if len(argv) == 2 and argv[0] == "create":
            print(f"Backup written: {create(settings, Path(argv[1]))}")
            return 0
        if len(argv) == 2 and argv[0] == "check":
            result = check(settings, Path(argv[1]))
        elif len(argv) == 3 and argv[0] == "restore":
            result = restore(settings, Path(argv[1]), Path(argv[2]))
        else:
            print(__doc__)
            return 2
    except BackupError as exc:
        print(exc)
        return 1
    problems = result.pop("problems")
    for problem in problems:
        print("PROBLEM:", problem)
    print(json.dumps(result, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
