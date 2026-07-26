from app.core.config import Settings


def test_bare_postgresql_url_gets_psycopg_driver() -> None:
    settings = Settings(database_url="postgresql://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_heroku_style_postgres_url_gets_psycopg_driver() -> None:
    settings = Settings(database_url="postgres://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_explicit_driver_is_preserved() -> None:
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert Settings(database_url=url).database_url == url


def test_resolved_jwks_url_derived_from_issuer() -> None:
    settings = Settings(clerk_issuer="https://x.clerk.accounts.dev/")
    assert settings.resolved_jwks_url == "https://x.clerk.accounts.dev/.well-known/jwks.json"
