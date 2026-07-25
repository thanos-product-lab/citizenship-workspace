from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi.testclient import TestClient

from app.auth import jwks
from app.core.config import Settings, get_settings
from app.main import app
from tests.auth._helpers import ISSUER, generate_keypair, make_token


@pytest.fixture(scope="module")
def key() -> RSAPrivateKey:
    return generate_keypair()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(clerk_issuer=ISSUER)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_me_returns_user_for_valid_token(
    client: TestClient, key: RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jwks, "get_signing_key", lambda _token: key.public_key())
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {make_token(key)}"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "user_123", "session_id": "sess_1", "email": None}


def test_me_rejects_missing_authorization(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401


def test_me_rejects_unknown_kid(
    client: TestClient, key: RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_unknown(_token: str) -> object:
        raise jwt.PyJWKClientError("no matching key")

    monkeypatch.setattr(jwks, "get_signing_key", raise_unknown)
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {make_token(key)}"})
    assert resp.status_code == 401


def test_me_fails_closed_when_issuer_unconfigured(
    key: RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid signature must not be accepted when no issuer is configured."""
    app.dependency_overrides[get_settings] = lambda: Settings(clerk_issuer="")
    monkeypatch.setattr(jwks, "get_signing_key", lambda _token: key.public_key())
    try:
        resp = TestClient(app).get(
            "/api/v1/me", headers={"Authorization": f"Bearer {make_token(key)}"}
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
