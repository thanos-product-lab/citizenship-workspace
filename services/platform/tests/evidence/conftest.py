"""Fixtures for the evidence suite, and the guard that keeps its security half honest.

The suite is deliberately split in two, and the split is load-bearing:

- `test_storage_fake.py` uses the in-process store and asserts **behaviour** — a key
  round-trips, an absent key reports absent, a presigned URL is produced. It is not
  permitted to assert a security property, because it could only ever assert one about
  itself.
- `test_storage_minio.py` runs against a real MinIO and is the **only** place that may
  assert a bucket is private, a URL expires, or a deleted object is gone. Those are
  properties of the storage service, not of our code.

A security test that silently skips reports green, which is the same failure the M5
harness was built to end. Two guards, because each is blind to what the other catches:

1. `minio_storage` **fails** rather than skips wherever `CW_EXPECT_MINIO` is set, so an
   unreachable store in CI is a red run, not a quiet one.
2. `test_storage_integration_tests_actually_ran` asserts the marked tests were collected
   at all, which is what catches the marker being renamed or the file being deleted —
   a case the fixture never gets the chance to see.
"""

import os
import pathlib
from collections.abc import Iterator

import pytest

from app.core.config import Settings
from app.core.storage import S3Storage, StorageError

_MINIO_MARKER = "minio"

# Filled in by the collection hook below; read by the guard test.
collected_minio_tests = 0


def minio_is_expected() -> bool:
    """True where a live MinIO is part of the contract (CI, and any dev box that says so)."""
    return os.environ.get("CW_EXPECT_MINIO") == "1"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    global collected_minio_tests
    collected_minio_tests = sum(
        1 for item in items if item.get_closest_marker(_MINIO_MARKER) is not None
    )


@pytest.fixture
def minio_settings() -> Settings:
    return Settings(
        storage_backend="s3",
        storage_endpoint_url=os.environ.get("STORAGE_ENDPOINT_URL", "http://localhost:9000"),
        storage_bucket=os.environ.get("STORAGE_BUCKET", "citizenship-evidence-test"),
        storage_access_key=os.environ.get("STORAGE_ACCESS_KEY", "minioadmin"),
        storage_secret_key=os.environ.get("STORAGE_SECRET_KEY", "minioadmin"),
        # Read from the environment like the rest, so this suite can be pointed at any
        # S3-compatible provider and not only MinIO. That is the point of it: these are
        # the assertions that decide whether a store is usable — a private bucket, an
        # expiring URL, a size limit the store itself enforces, a deleted object that
        # stays deleted — so running them against a candidate provider answers "will this
        # work" with the same code that guards the real thing.
        #
        # Region matters here in a way it does not locally. MinIO ignores it; Cloudflare
        # R2 requires `auto` and rejects the signature otherwise, which surfaces as an
        # opaque `SignatureDoesNotMatch` rather than anything about regions.
        storage_region=os.environ.get("STORAGE_REGION", "us-east-1"),
    )


@pytest.fixture
def minio_storage(minio_settings: Settings) -> Iterator[S3Storage]:
    """A real bucket, or a failure where one was promised.

    `pytest.skip` here would be the whole problem: an unreachable store would take the
    storage security assertions out of the run while the run still reported green.
    """
    storage = S3Storage(minio_settings)
    try:
        storage.ensure_bucket()
    except (StorageError, OSError) as exc:
        if minio_is_expected():
            pytest.fail(
                "CW_EXPECT_MINIO is set but MinIO is unreachable, so the storage "
                f"security assertions did not run: {str(exc)[:200]}"
            )
        pytest.skip("no MinIO available; set CW_EXPECT_MINIO=1 to make this a failure")
    yield storage


#: Where `scripts/make_fixtures.py` writes the synthetic documents.
FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "documents"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
