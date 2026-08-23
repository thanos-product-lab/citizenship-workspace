"""Storage **security** properties, against a real MinIO.

This is the only file permitted to assert that a bucket is private, that a presigned
URL expires, or that a deleted object is gone. Those are properties of the storage
service; the in-process fake has no bucket policy to be wrong about and no clock to run
out, so a test of it could only ever assert something about itself.

Marked `minio`. Where `CW_EXPECT_MINIO=1` (CI), an unreachable store fails the run
rather than skipping it — see `conftest.py`.
"""

import time
import uuid

import httpx
import pytest

from app.core.storage import S3Storage, build_key

pytestmark = pytest.mark.minio

_BODY = b"%PDF-1.7 hello"


def _key() -> str:
    return build_key(case_id=uuid.uuid4(), evidence_item_id=uuid.uuid4())


def _put(url: str, body: bytes, media_type: str) -> int:
    return httpx.put(url, content=body, headers={"Content-Type": media_type}).status_code


def _upload(storage: S3Storage) -> str:
    """Put one object there through the presigned path a real client would use."""
    key = _key()
    url = storage.presigned_put_url(key, media_type="application/pdf", ttl_seconds=60)
    assert _put(url, _BODY, "application/pdf") == 200
    return key


def test_an_object_is_not_readable_without_a_signature(minio_storage: S3Storage) -> None:
    """The property the whole milestone rests on: MVP §8.9, "Documents are not publicly
    accessible." An unsigned GET at the object's own address must be refused."""
    key = _upload(minio_storage)

    unsigned = f"{minio_storage.endpoint_url}/{minio_storage.bucket}/{key}"
    assert httpx.get(unsigned).status_code in {401, 403}


def test_a_presigned_url_stops_working_when_it_expires(minio_storage: S3Storage) -> None:
    """MVP §8.9: "Upload URLs expire." A presigned URL cannot be revoked (ADR-0018), so
    its TTL is the entire bound on its life — which makes the TTL actually elapsing the
    only thing standing between an issued URL and an indefinite one."""
    key = _upload(minio_storage)

    url = minio_storage.presigned_get_url(key, ttl_seconds=1)
    assert httpx.get(url).status_code == 200
    time.sleep(2)
    assert httpx.get(url).status_code == 403


def test_an_old_signed_url_cannot_reach_a_deleted_object(minio_storage: S3Storage) -> None:
    """MVP §8.9: "Old signed URLs cannot access deleted files." Not because the URL is
    revoked — it is not — but because there is nothing behind it once the purge runs.
    This is the assertion that makes Domain §51.1 step 3 mean something."""
    key = _upload(minio_storage)

    url = minio_storage.presigned_get_url(key, ttl_seconds=300)
    assert httpx.get(url).status_code == 200

    minio_storage.delete(key)
    assert httpx.get(url).status_code == 404
    assert minio_storage.head(key) is None


def test_an_upload_cannot_declare_a_different_content_type_than_the_one_signed(
    minio_storage: S3Storage,
) -> None:
    """ContentType is part of the signature, so the media type the server authorised is
    the media type that can be uploaded. This is the first half of "unsupported file
    types are rejected before processing" — the magic-byte check in the worker is the
    second, because a client controls the bytes even when it cannot control the label."""
    key = _key()
    url = minio_storage.presigned_put_url(key, media_type="application/pdf", ttl_seconds=60)
    assert _put(url, b"MZ\x90\x00", "application/x-msdownload") == 403


def test_the_download_disposition_reaches_the_response(minio_storage: S3Storage) -> None:
    key = _upload(minio_storage)

    url = minio_storage.presigned_get_url(key, ttl_seconds=60, download_filename="a\r\nb.pdf")
    disposition = httpx.get(url).headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
