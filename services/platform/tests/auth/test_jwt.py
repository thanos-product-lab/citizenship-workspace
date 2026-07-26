from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.auth.dependencies import decode_clerk_jwt
from app.core.config import Settings
from tests.auth._helpers import ISSUER, generate_keypair, make_token


@pytest.fixture(scope="module")
def key() -> RSAPrivateKey:
    return generate_keypair()


def make_settings(*, clerk_authorized_parties: str = "") -> Settings:
    # Explicit fields override any local .env (init kwargs win), keeping tests
    # deterministic regardless of the developer's environment.
    return Settings(
        clerk_issuer=ISSUER,
        clerk_audience=None,
        clerk_authorized_parties=clerk_authorized_parties,
    )


def test_valid_token_decodes(key: RSAPrivateKey) -> None:
    claims = decode_clerk_jwt(make_token(key), key.public_key(), make_settings())
    assert claims["sub"] == "user_123"


def test_expired_rejected(key: RSAPrivateKey) -> None:
    token = make_token(key, exp=datetime.now(UTC) - timedelta(minutes=1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_clerk_jwt(token, key.public_key(), make_settings())


def test_small_clock_skew_is_tolerated(key: RSAPrivateKey) -> None:
    # Server clock behind the issuer: an iat slightly in the future is accepted.
    token = make_token(key, iat=datetime.now(UTC) + timedelta(seconds=30))
    assert decode_clerk_jwt(token, key.public_key(), make_settings())["sub"] == "user_123"


def test_large_clock_skew_rejected(key: RSAPrivateKey) -> None:
    token = make_token(key, iat=datetime.now(UTC) + timedelta(minutes=5))
    with pytest.raises(jwt.ImmatureSignatureError):
        decode_clerk_jwt(token, key.public_key(), make_settings())


def test_wrong_issuer_rejected(key: RSAPrivateKey) -> None:
    token = make_token(key, iss="https://evil.example")
    with pytest.raises(jwt.InvalidIssuerError):
        decode_clerk_jwt(token, key.public_key(), make_settings())


def test_bad_signature_rejected(key: RSAPrivateKey) -> None:
    other = generate_keypair()
    with pytest.raises(jwt.InvalidSignatureError):
        decode_clerk_jwt(make_token(key), other.public_key(), make_settings())


def test_alg_none_rejected(key: RSAPrivateKey) -> None:
    now = datetime.now(UTC)
    unsigned = jwt.encode(
        {"sub": "user_123", "iss": ISSUER, "iat": now, "exp": now + timedelta(minutes=5)},
        "",
        algorithm="none",
    )
    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_clerk_jwt(unsigned, key.public_key(), make_settings())


def test_missing_exp_rejected(key: RSAPrivateKey) -> None:
    token = jwt.encode({"sub": "user_123", "iss": ISSUER, "iat": datetime.now(UTC)}, key, "RS256")
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_clerk_jwt(token, key.public_key(), make_settings())


def test_authorized_party_allowed(key: RSAPrivateKey) -> None:
    token = make_token(key, azp="http://localhost:3000")
    settings = make_settings(clerk_authorized_parties="http://localhost:3000")
    assert decode_clerk_jwt(token, key.public_key(), settings)["azp"] == "http://localhost:3000"


def test_unauthorized_party_rejected(key: RSAPrivateKey) -> None:
    token = make_token(key, azp="http://evil.example")
    settings = make_settings(clerk_authorized_parties="http://localhost:3000")
    with pytest.raises(jwt.InvalidTokenError):
        decode_clerk_jwt(token, key.public_key(), settings)
