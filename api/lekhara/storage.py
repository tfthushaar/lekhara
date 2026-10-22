"""File storage for the document vault.

Files are addressed by the SHA-256 of their contents, so the same file uploaded twice
is stored once and a stored file can never change under its key. On local disk for development
and small setups; in an S3 bucket (or any S3-compatible store) in production, encrypted at rest
and with S3 checking each upload against its SHA-256. `make_storage` picks one from the
settings: LEKHARA_STORAGE_URL=s3://bucket/prefix for S3, otherwise LEKHARA_STORAGE_DIR.
"""

import base64
import contextlib
import hashlib
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

if TYPE_CHECKING:
    from lekhara.config import Settings

_KEY = re.compile(r"^[0-9a-f]{64}$")


class Storage(Protocol):
    def put(self, data: bytes) -> str: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def keys(self) -> Iterator[str]: ...


def _check_key(key: str) -> str:
    if not _KEY.match(key):
        raise ValueError("Not a storage key")
    return key


class LocalStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _check_key(key)[:2] / key

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

    def keys(self) -> Iterator[str]:
        """Every stored file's key, for backups."""
        if self.root.exists():
            for path in self.root.rglob("*"):
                if path.is_file() and _KEY.match(path.name):
                    yield path.name


class S3Storage:
    """Files in an S3 bucket under a prefix, each named like on disk (ab/abcd...).

    Every upload carries its SHA-256, which S3 checks before keeping the file, and asks for
    encryption at rest: AES256 (S3's own keys), aws:kms (a KMS key, given or the account's
    default), or none for a store that does not support it. Credentials come the usual AWS way
    (the server's role, or AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY); boto3 is needed, from
    the s3 extra.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        region: str | None = None,
        endpoint: str | None = None,
        encryption: str = "AES256",
        kms_key_id: str | None = None,
        client=None,
    ) -> None:
        if encryption not in ("AES256", "aws:kms", "none"):
            raise ValueError("Encryption is AES256, aws:kms or none.")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.encryption = encryption
        self.kms_key_id = kms_key_id
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region, endpoint_url=endpoint or None)
        self.client = client

    def _name(self, key: str) -> str:
        path = f"{_check_key(key)[:2]}/{key}"
        return f"{self.prefix}/{path}" if self.prefix else path

    def _missing(self, exc: Exception) -> bool:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        return code in ("404", "NoSuchKey", "NotFound")

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).digest()
        key = digest.hex()
        name = self._name(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=name)
            return key  # already stored: the same bytes, by its name
        except Exception as exc:
            if not self._missing(exc):
                raise
        extra = {}
        if self.encryption != "none":
            extra["ServerSideEncryption"] = self.encryption
        if self.encryption == "aws:kms" and self.kms_key_id:
            extra["SSEKMSKeyId"] = self.kms_key_id
        self.client.put_object(
            Bucket=self.bucket,
            Key=name,
            Body=data,
            ChecksumSHA256=base64.b64encode(digest).decode(),
            ContentType="application/octet-stream",
            **extra,
        )
        return key

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._name(key))
        except Exception as exc:
            if self._missing(exc):
                raise FileNotFoundError(key) from None
            raise
        return response["Body"].read()

    def delete(self, key: str) -> None:
        with contextlib.suppress(ValueError):
            self.client.delete_object(Bucket=self.bucket, Key=self._name(key))

    def keys(self) -> Iterator[str]:
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=f"{self.prefix}/" if self.prefix else ""
        )
        for page in pages:
            for item in page.get("Contents", []):
                name = item["Key"].rsplit("/", 1)[-1]
                if _KEY.match(name):
                    yield name


def make_storage(settings: "Settings") -> Storage:
    """The store the settings name: an S3 bucket for s3://bucket/prefix, else local disk."""
    url = (settings.storage_url or "").strip()
    if not url:
        return LocalStorage(settings.storage_dir)
    parsed = urlparse(url)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError("LEKHARA_STORAGE_URL must look like s3://bucket/prefix.")
    return S3Storage(
        parsed.netloc,
        parsed.path,
        region=settings.s3_region,
        endpoint=settings.s3_endpoint,
        encryption=settings.s3_encryption,
        kms_key_id=settings.s3_kms_key_id,
    )
