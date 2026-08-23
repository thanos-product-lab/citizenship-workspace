"""Behaviour of the in-process store — and nothing about security.

Every assertion here is about the contract `StorageAdapter` promises: what a key does,
what an absent key does, what `build_key` guarantees. If you find yourself wanting to
assert that something is *private* or *expired*, it belongs in `test_storage_minio.py`;
this store has no bucket policy to be wrong about and no clock to run out.
"""

import uuid

import pytest

from app.core.storage import (
    InMemoryStorage,
    build_key,
    content_disposition,
)


@pytest.fixture
def store() -> InMemoryStorage:
    return InMemoryStorage()


def test_a_stored_object_reports_its_size(store: InMemoryStorage) -> None:
    store.put("k", b"hello world")
    stored = store.head("k")
    assert stored is not None
    assert stored.size_bytes == 11


def test_an_absent_key_reports_absent_rather_than_raising(store: InMemoryStorage) -> None:
    assert store.head("never-written") is None


def test_delete_is_idempotent(store: InMemoryStorage) -> None:
    """Domain §51.1 deletion is redelivered at-least-once, so deleting twice must be
    as safe as deleting once."""
    store.put("k", b"x")
    store.delete("k")
    store.delete("k")
    assert store.head("k") is None


def test_presigning_returns_the_key_and_the_policy_fields(store: InMemoryStorage) -> None:
    signed = store.presigned_upload(
        "k", media_type="application/pdf", ttl_seconds=60, max_bytes=1024
    )
    assert signed.fields["key"] == "k"
    assert signed.fields["Content-Type"] == "application/pdf"


# --- storage keys ------------------------------------------------------------------


def test_two_keys_for_the_same_case_never_collide() -> None:
    """The random component is what makes a key unguessable. Without it, knowing a case
    id would be enough to name the object."""
    case_id = uuid.uuid4()
    keys = {build_key(case_id=case_id) for _ in range(100)}
    assert len(keys) == 100


def test_a_key_never_contains_the_original_filename() -> None:
    """Threat model §12: original filenames are metadata only and never determine
    storage paths. The signature makes this true by construction — there is no filename
    parameter to pass — and this test is what stops one being added."""
    import inspect

    assert "filename" not in inspect.signature(build_key).parameters


# --- Content-Disposition -----------------------------------------------------------
#
# `original_filename` is untrusted input reaching an HTTP header. These are behaviour
# tests of the encoder, not of any live response.


@pytest.mark.parametrize(
    "hostile",
    [
        "report.pdf\r\nX-Injected: yes",
        "report.pdf\nSet-Cookie: a=b",
        "report.pdf\rLocation: http://evil.example",
    ],
)
def test_a_filename_cannot_split_the_header(hostile: str) -> None:
    """CWE-93 / CWE-113. React escapes a filename in the library view; a header does not,
    so the encoding happens once, here, at the boundary."""
    header = content_disposition(hostile)
    assert "\r" not in header
    assert "\n" not in header
    assert "X-Injected" not in header
    assert "Set-Cookie" not in header


def test_a_quote_cannot_escape_the_quoted_string() -> None:
    header = content_disposition('a".pdf')
    ascii_part = header.split("filename*=")[0]
    assert ascii_part.count('"') == 2


def test_a_non_ascii_name_survives_in_the_extended_form() -> None:
    header = content_disposition("Αθήνα.pdf")
    assert "filename*=UTF-8''" in header
    assert "%CE%91" in header  # the capital alpha, percent-encoded


def test_a_name_with_nothing_usable_falls_back_rather_than_emitting_an_empty_filename() -> None:
    assert 'filename="document"' in content_disposition("\r\n\r\n")
    assert 'filename="document"' in content_disposition(None)
