"""The upload path, through the real HTTP commands.

Two calls with a direct-to-storage PUT between them, and only the second writes:

    POST .../evidence/uploads   -> a presigned PUT URL and a signed token
    (the browser PUTs the bytes; here the fake store is written directly)
    POST .../evidence           -> the document is recorded

Covers what each call refuses, that an abandoned upload leaves nothing behind, and the
ownership boundary. The store is the in-process fake, so every assertion here is about
behaviour. Storage *security* properties are in `test_storage_minio.py`, and nothing
here may claim them.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.storage import InMemoryStorage, get_storage
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

_PDF = b"%PDF-1.7 a synthetic, fictional document"


def _active_case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    assert (
        api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS).status_code
        == 200
    )
    confirmed = api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert confirmed.json()["lifecycle_status"] == "ACTIVE"
    return case_id


def _url(case_id: str) -> str:
    return f"/api/v1/cases/{case_id}/evidence"


def _store() -> InMemoryStorage:
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    return store


def _key_from(upload_url: str) -> str:
    """The fake's presigned URL is `memory://put/<key>?…`; recover the key from it.

    Deliberately parsed rather than returned in the response: the client never learns
    the storage key as a field, only as an opaque token, and the test holds itself to
    the same shape.
    """
    return upload_url.removeprefix("memory://put/").split("?", 1)[0]


def _start(api: Api, user: str, case_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"media_type": "application/pdf", "declared_size_bytes": len(_PDF)}
    body.update(overrides)
    return dict(api(user).post(f"{_url(case_id)}/uploads", json=body).json())


def _record(api: Api, user: str, case_id: str, token: str, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "upload_token": token,
        "category": "TRAVEL_SUPPORT",
        "display_name": "Athens booking",
        "original_filename": "booking.pdf",
    }
    body.update(overrides)
    return api(user).post(_url(case_id), json=body)


def _upload(api: Api, user: str, case_id: str) -> Any:
    """The whole happy path: grant, PUT the bytes, record."""
    grant = _start(api, user, case_id)
    _store().put(_key_from(str(grant["upload_url"])), _PDF)
    return _record(api, user, case_id, str(grant["upload_token"]))


# --- starting an upload ------------------------------------------------------------


def test_starting_an_upload_returns_a_url_and_a_token(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    assert grant["upload_url"]
    assert grant["upload_token"]
    assert grant["media_type"] == "application/pdf"
    assert grant["expires_in_seconds"] > 0


def test_starting_an_upload_writes_nothing(api: Api) -> None:
    """A presigned URL that is never used must leave nothing behind — no orphan row, no
    item that reads as a document the case holds."""
    case_id = _active_case(api, "user_a")
    _start(api, "user_a", case_id)
    assert api("user_a").get(_url(case_id)).json()["items"] == []


def test_an_unsupported_media_type_is_refused_before_anything_is_uploaded(api: Api) -> None:
    """MVP §8.9: unsupported file types are rejected *before* processing. Refusing here
    means the user finds out before waiting for an upload, and no object is ever written
    for a type this product cannot read."""
    case_id = _active_case(api, "user_a")
    response = api("user_a").post(
        f"{_url(case_id)}/uploads",
        json={"media_type": "application/x-msdownload", "declared_size_bytes": 10},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_EVIDENCE_TYPE"
    assert "application/pdf" in response.json()["supported"]


def test_an_oversized_declaration_is_refused_before_anything_is_uploaded(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    response = api("user_a").post(
        f"{_url(case_id)}/uploads",
        json={"media_type": "application/pdf", "declared_size_bytes": 999_999_999},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "EVIDENCE_TOO_LARGE"


# --- recording the upload ----------------------------------------------------------


def test_recording_an_upload_makes_it_visible_evidence(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    recorded = _upload(api, "user_a", case_id)

    assert recorded.status_code == 201
    body = recorded.json()
    assert body["processing_status"] == "UPLOADED"
    assert body["size_bytes"] == len(_PDF)

    library = api("user_a").get(_url(case_id)).json()
    assert [item["id"] for item in library["items"]] == [body["id"]]


def test_recording_without_the_bytes_records_nothing(api: Api) -> None:
    """The presigned URL was issued and never used. An item whose content is absent is
    not evidence and must not be recorded as though it were."""
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)

    response = _record(api, "user_a", case_id, str(grant["upload_token"]))
    assert response.status_code == 409
    assert response.json()["code"] == "EVIDENCE_UPLOAD_INCOMPLETE"
    assert api("user_a").get(_url(case_id)).json()["items"] == []


def test_the_size_recorded_is_the_stores_count_not_the_clients_claim(api: Api) -> None:
    """A client controls what it declares, not what it uploads. The number on the record
    has to be the one the store reports."""
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id, declared_size_bytes=1)
    _store().put(_key_from(str(grant["upload_url"])), _PDF)

    body = _record(api, "user_a", case_id, str(grant["upload_token"])).json()
    assert body["size_bytes"] == len(_PDF) != 1


# --- the token ---------------------------------------------------------------------


def test_an_altered_token_is_refused(api: Api) -> None:
    """The token is what stops a client choosing its own storage path (threat model
    §12). Editing any part of it must invalidate the signature."""
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    _store().put(_key_from(str(grant["upload_url"])), _PDF)

    body, signature = str(grant["upload_token"]).split(".", 1)
    tampered = f"{body[:-2]}XY.{signature}"

    response = _record(api, "user_a", case_id, tampered)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_UPLOAD_GRANT"
    assert api("user_a").get(_url(case_id)).json()["items"] == []


def test_a_token_minted_for_one_case_cannot_be_used_on_another(api: Api) -> None:
    """Both cases are the same user's, so ownership does not separate them — RLS does
    not hide the caller's own other cases. The token's bound case id does."""
    first = _active_case(api, "user_a")
    second = _active_case(api, "user_a")
    grant = _start(api, "user_a", first)
    _store().put(_key_from(str(grant["upload_url"])), _PDF)

    response = _record(api, "user_a", second, str(grant["upload_token"]))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_UPLOAD_GRANT"


def test_a_garbage_token_is_refused_without_reaching_the_parser(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    for junk in ("", "not-a-token", "a.b", "...."):
        response = _record(api, "user_a", case_id, junk)
        assert response.status_code == 422, junk
        assert response.json()["code"] == "INVALID_UPLOAD_GRANT"


# --- ownership ---------------------------------------------------------------------


def test_another_user_cannot_read_the_evidence_library(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    item_id = _upload(api, "user_a", case_id).json()["id"]

    assert api("user_b").get(_url(case_id)).status_code == 404
    assert api("user_b").get(f"{_url(case_id)}/{item_id}").status_code == 404
    assert api("user_b").get(f"{_url(case_id)}/{item_id}/content").status_code == 404


def test_an_evidence_id_from_another_case_is_not_reachable(api: Api) -> None:
    """RLS hides another *tenant*; it does not hide the caller's own other cases, so the
    case-ownership of a nested object is checked explicitly (Domain §3.1)."""
    first = _active_case(api, "user_a")
    second = _active_case(api, "user_a")
    item_id = _upload(api, "user_a", first).json()["id"]

    assert api("user_a").get(f"{_url(second)}/{item_id}").status_code == 404
    assert api("user_a").get(f"{_url(second)}/{item_id}/content").status_code == 404


def test_an_unknown_id_is_indistinguishable_from_one_that_is_not_yours(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    unknown = api("user_a").get(f"{_url(case_id)}/{uuid.uuid4()}")
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Evidence not found"


# --- content -----------------------------------------------------------------------


def test_a_content_url_is_issued_only_after_the_ownership_check(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    item_id = _upload(api, "user_a", case_id).json()["id"]

    body = api("user_a").get(f"{_url(case_id)}/{item_id}/content").json()
    assert body["url"]
    assert body["expires_in_seconds"] > 0


def test_the_response_never_carries_the_storage_key(api: Api) -> None:
    """A key is not a permission (Domain §52), but it is also not the client's business:
    nothing it can see should name where the object lives."""
    case_id = _active_case(api, "user_a")
    recorded = _upload(api, "user_a", case_id).json()
    assert "storage_key" not in recorded
    assert "cases/" not in str(recorded)


# --- case lifecycle ----------------------------------------------------------------


def test_evidence_cannot_be_added_to_a_case_that_is_not_active(api: Api) -> None:
    """A draft case is still choosing its route, so there is nothing for evidence to
    support yet. A 409 with a code, not a 404: the case is real and owned, just not
    ready."""
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "Draft"}).json()["id"])
    response = api("user_a").post(
        f"{_url(case_id)}/uploads",
        json={"media_type": "application/pdf", "declared_size_bytes": 10},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CASE_NOT_ACTIVE"
