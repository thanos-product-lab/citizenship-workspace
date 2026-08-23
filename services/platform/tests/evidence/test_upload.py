"""The upload path, through the real HTTP commands.

Two calls with a direct-to-storage upload between them, and only the second writes:

    POST .../evidence/uploads   -> a presigned POST form and a signed token
    (the browser posts the bytes; here the fake store is written directly)
    POST .../evidence           -> the document is recorded

Covers what each call refuses, that an abandoned upload leaves nothing behind, and the
ownership boundary. The store is the in-process fake, so every assertion here is about
behaviour. Storage *security* properties are in `test_storage_minio.py`, and nothing
here may claim them.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.storage import InMemoryStorage, get_storage
from app.evidence import upload_token
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

_PDF = b"%PDF-1.7 a synthetic, fictional document"

#: Comfortably past the presign TTL, whatever it is configured to.
_EXPIRY_OVERSHOOT = 3600


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


def _key_from(grant: dict[str, Any]) -> str:
    """The storage key the grant authorises.

    A presigned POST names its key in the signed fields, so the client does see it —
    Domain §52 makes that harmless, since a key is not a permission. What stays true is
    narrower and is asserted separately: no *response body* describing a document names
    where its object lives.
    """
    fields = grant["upload_fields"]
    assert isinstance(fields, dict)
    return str(fields["key"])


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
    _store().put(_key_from(grant), _PDF)
    return _record(api, user, case_id, str(grant["upload_token"]))


# --- starting an upload ------------------------------------------------------------


def test_starting_an_upload_returns_a_url_and_a_token(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    assert grant["upload_url"]
    assert grant["upload_token"]
    assert grant["media_type"] == "application/pdf"
    assert grant["expires_in_seconds"] > 0
    # The signed policy fields, which carry the ceiling the store will enforce.
    assert "key" in grant["upload_fields"]


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
    _store().put(_key_from(grant), _PDF)

    body = _record(api, "user_a", case_id, str(grant["upload_token"])).json()
    assert body["size_bytes"] == len(_PDF) != 1


def test_recording_the_same_upload_twice_returns_the_same_document(api: Api) -> None:
    """Recording is idempotent on the storage key.

    This is the retry-prone call: the bytes are already in the store, so a client that
    loses the response sends it again. Without idempotency the retry violates
    `uq_evidence_files_storage_key`, and the resulting IntegrityError renders SQLAlchemy's
    bound parameters — the storage key, the original filename and the checksum — into a
    500 and from there into the logs. Threat model §6.4 forbids exactly that, and it is
    reachable without malice.
    """
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    _store().put(_key_from(grant), _PDF)
    token = str(grant["upload_token"])

    first = _record(api, "user_a", case_id, token)
    second = _record(api, "user_a", case_id, token)

    assert first.status_code == 201
    assert second.status_code < 400, second.text
    assert second.json()["id"] == first.json()["id"]
    # One document, not two, and no second file version.
    assert len(api("user_a").get(_url(case_id)).json()["items"]) == 1


def test_a_retried_recording_never_puts_the_key_or_the_filename_in_an_error(
    api: Api,
) -> None:
    """The specific leak the idempotency exists to close. A 500 here would carry the
    storage key, `booking.pdf` and the checksum in its body and its traceback."""
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    _store().put(_key_from(grant), _PDF)
    token = str(grant["upload_token"])

    _record(api, "user_a", case_id, token)
    retried = _record(api, "user_a", case_id, token)

    # The filename is legitimately in the response — it is the document's own metadata,
    # returned to the document's owner, exactly as the first call returned it. What must
    # never appear is the storage key, and what must never happen is the 500 whose
    # traceback carries the key, the filename and the checksum together into the logs.
    assert retried.status_code != 500
    assert _key_from(grant) not in retried.text
    assert "storage_key" not in retried.text


# --- the token ---------------------------------------------------------------------


def test_an_altered_token_is_refused(api: Api) -> None:
    """The token is what stops a client choosing its own storage path (threat model
    §12). Editing any part of it must invalidate the signature."""
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    _store().put(_key_from(grant), _PDF)

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
    _store().put(_key_from(grant), _PDF)

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


def test_no_document_response_names_where_its_object_lives(api: Api) -> None:
    """A key is not a permission (Domain §52) and the upload grant necessarily contains
    one — a presigned POST names its key in the signed fields. What must not happen is a
    document's own representation carrying it: nothing in the library, the detail or the
    content response should say where the bytes are."""
    case_id = _active_case(api, "user_a")
    item_id = _upload(api, "user_a", case_id).json()["id"]

    # The content response is excluded on purpose: a presigned GET *is* the object's
    # address, so it names the key by construction. That is Domain §52's point rather
    # than a violation of it — the URL is short-lived and issued only after the
    # ownership check, and possessing it still confers nothing on any other object.
    for path in ("", f"/{item_id}"):
        body = str(api("user_a").get(f"{_url(case_id)}{path}").json())
        assert "storage_key" not in body
        assert "cases/" not in body


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


# --- the token's expiry ------------------------------------------------------------


def test_an_expired_token_is_refused(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """The token cannot outlive the URL it accompanies. ADR-0019 names expiry as one of
    the three things the signature binds, and the other two are covered above."""
    case_id = _active_case(api, "user_a")
    grant = _start(api, "user_a", case_id)
    _store().put(_key_from(grant), _PDF)

    # Move the clock past the TTL rather than sleeping through it.
    real_now = int(time.time())
    monkeypatch.setattr(upload_token, "_now", lambda: real_now + _EXPIRY_OVERSHOOT)

    response = _record(api, "user_a", case_id, str(grant["upload_token"]))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_UPLOAD_GRANT"
    assert api("user_a").get(_url(case_id)).json()["items"] == []


# --- boot configuration -------------------------------------------------------------


@pytest.mark.parametrize("environment", ["production", "staging", "railway"])
def test_a_deployed_environment_refuses_to_boot_without_a_signing_secret(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard that took a deployment down, pinned so it stays deliberate.

    A per-process key is fine for one instance and silently wrong for two: a token signed
    by one replica is rejected by the other, and the symptom is intermittent 422s that
    look exactly like tampering.
    """
    from app.core.config import Settings
    from app.evidence.upload_token import check_upload_secret

    monkeypatch.setattr(
        "app.evidence.upload_token.get_settings",
        lambda: Settings(environment=environment, upload_token_secret=""),
    )
    with pytest.raises(RuntimeError) as raised:
        check_upload_secret()

    # The message has to distinguish the four ways this goes wrong on a platform, so it
    # names what it observed rather than only what it wanted.
    assert environment in str(raised.value)
    assert "UPLOAD_TOKEN_SECRET" in str(raised.value)


@pytest.mark.parametrize("environment", ["local", "docker", "test"])
def test_local_development_still_boots_without_one(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import Settings
    from app.evidence.upload_token import check_upload_secret

    monkeypatch.setattr(
        "app.evidence.upload_token.get_settings",
        lambda: Settings(environment=environment, upload_token_secret=""),
    )
    check_upload_secret()


def test_a_secret_too_short_to_be_worth_configuring_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shorter than the 32-byte fallback it replaces is a downgrade wearing a config."""
    from app.core.config import Settings
    from app.evidence.upload_token import check_upload_secret

    monkeypatch.setattr(
        "app.evidence.upload_token.get_settings",
        lambda: Settings(environment="production", upload_token_secret="short"),
    )
    with pytest.raises(RuntimeError, match="at least 32"):
        check_upload_secret()


def test_the_configuration_line_reports_presence_and_never_a_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Presence is not a secret; the value is. This line exists so "is it actually set?"
    is answerable from the logs rather than from a stack trace."""
    from app.core.config import Settings
    from app.main import _log_configuration

    secret = "s" * 40
    _log_configuration(Settings(environment="production", upload_token_secret=secret))

    rendered = "".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered
