"""File storage: on local disk, and in S3 (checked with botocore's Stubber, without a bucket)."""

import base64
import hashlib
import io

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from lekhara.config import Settings
from lekhara.storage import LocalStorage, S3Storage, make_storage

DATA = b"%PDF-1.4 a sanctioned plan"
KEY = hashlib.sha256(DATA).hexdigest()
NAME = f"vault/{KEY[:2]}/{KEY}"


def s3(**kwargs) -> tuple[S3Storage, Stubber]:
    client = boto3.client(
        "s3", region_name="ap-south-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    return S3Storage("lekhara-files", "/vault/", client=client, **kwargs), Stubber(client)


def test_local_storage_keeps_files_by_their_fingerprint(tmp_path) -> None:
    store = LocalStorage(tmp_path)
    assert store.put(DATA) == KEY and store.put(DATA) == KEY
    assert store.get(KEY) == DATA and list(store.keys()) == [KEY]
    store.delete(KEY)
    assert list(store.keys()) == []
    with pytest.raises(ValueError):
        store.get("../../etc/passwd")


def test_s3_upload_is_checked_and_encrypted() -> None:
    store, stub = s3()
    stub.add_client_error("head_object", "404", http_status_code=404,
                          expected_params={"Bucket": "lekhara-files", "Key": NAME})  # fmt: skip
    stub.add_response(
        "put_object",
        {},
        {
            "Bucket": "lekhara-files",
            "Key": NAME,
            "Body": DATA,
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(DATA).digest()).decode(),
            "ContentType": "application/octet-stream",
            "ServerSideEncryption": "AES256",
        },
    )
    with stub:
        assert store.put(DATA) == KEY
    stub.assert_no_pending_responses()


def test_s3_with_a_kms_key_and_a_file_already_there() -> None:
    store, stub = s3(encryption="aws:kms", kms_key_id="alias/lekhara")
    stub.add_response("head_object", {}, {"Bucket": "lekhara-files", "Key": NAME})
    with stub:
        assert store.put(DATA) == KEY  # the same bytes are not sent again
    store, stub = s3(encryption="aws:kms", kms_key_id="alias/lekhara")
    stub.add_client_error("head_object", "404", http_status_code=404)
    stub.add_response(
        "put_object",
        {},
        {
            "Bucket": "lekhara-files", "Key": NAME, "Body": DATA,
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(DATA).digest()).decode(),
            "ContentType": "application/octet-stream",
            "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": "alias/lekhara",
        },
    )  # fmt: skip
    with stub:
        store.put(DATA)


def test_s3_reads_lists_and_reports_missing_files() -> None:
    store, stub = s3()
    stub.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(DATA), len(DATA))},
        {"Bucket": "lekhara-files", "Key": NAME},
    )
    stub.add_client_error("get_object", "NoSuchKey", http_status_code=404)
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": NAME}, {"Key": "vault/README.txt"}], "IsTruncated": False},
        {"Bucket": "lekhara-files", "Prefix": "vault/"},
    )
    with stub:
        assert store.get(KEY) == DATA
        with pytest.raises(FileNotFoundError):
            store.get("0" * 64)
        assert list(store.keys()) == [KEY]


def test_settings_choose_the_store(tmp_path) -> None:
    assert isinstance(make_storage(Settings(storage_dir=str(tmp_path))), LocalStorage)
    store = make_storage(
        Settings(storage_url="s3://lekhara-files/vault", s3_endpoint="http://localhost:8333")
    )
    assert isinstance(store, S3Storage) and store.bucket == "lekhara-files"
    assert store.prefix == "vault"
    with pytest.raises(ValueError):
        make_storage(Settings(storage_url="https://example.com/files"))
    with pytest.raises(ValueError):
        S3Storage("b", client=object(), encryption="rot13")
