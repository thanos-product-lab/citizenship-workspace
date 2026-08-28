"""The boot guard for backing services, and the incident that produced it.

M7 deployed a Celery worker whose `REDIS_URL` never reached the process. It fell back to
the default in `app/core/config.py`, `redis://localhost:6379/0`, and retried for fifteen
minutes — reporting Online throughout, while the API accepted uploads that could never be
processed. Documents sat at `UPLOADED` with no error anywhere a user or an operator would
look.

Two guards came out of it, and they fail at different moments on purpose:

- `check_backing_services` gives the *named* error, and needs `ENVIRONMENT` to be set to
  fire at all.
- `broker_connection_retry_on_startup = False` needs nothing to be set, and is what
  covers the case where `ENVIRONMENT` is missing too — which is likely, since a
  deployment that lost one variable tends to have lost them together.

Both are tested here, because a guard nobody exercises is a comment.
"""

import pytest

from app.core.config import LOCAL_ENVIRONMENTS, Settings, check_backing_services

_DEPLOYED = ["production", "staging", "railway"]

#: What the defaults in `Settings` are, spelled out. If someone changes a default to a
#: real host these tests should be the thing that asks why.
_LOOPBACK_REDIS = "redis://localhost:6379/0"
_LOOPBACK_DB = "postgresql+psycopg://citizenship:citizenship@localhost:5432/citizenship"


#: Hosts that are not this container, for the cases that must *not* raise.
_REMOTE_REDIS = "redis://cache.internal:6379/0"
_REMOTE_DB = "postgresql+psycopg://u@db.internal:5432/app"


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str,
    redis_url: str = _LOOPBACK_REDIS,
    database_url: str = _LOOPBACK_DB,
) -> None:
    """Install a `Settings` the guard will read.

    Spelled out as three named parameters rather than `**overrides`, because `Settings`
    has fields that are not strings (`storage_backend` is a `Literal`, `max_upload_bytes`
    an `int`) and a `**kwargs: str` cannot type-check against them.
    """
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(environment=environment, redis_url=redis_url, database_url=database_url),
    )


@pytest.mark.parametrize("environment", _DEPLOYED)
def test_a_deployed_environment_refuses_to_boot_against_its_own_container(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact shape of the incident: the variable never arrived, so the default won."""
    _settings(monkeypatch, environment=environment)

    with pytest.raises(RuntimeError) as raised:
        check_backing_services()

    message = str(raised.value)
    assert "REDIS_URL" in message
    assert "DATABASE_URL" in message
    # Name what was observed, not only what was wanted — the same reason
    # `check_upload_secret` reports the environment it saw.
    assert environment in message


@pytest.mark.parametrize(
    ("variable", "redis_url", "database_url"),
    [
        ("REDIS_URL", _LOOPBACK_REDIS, _REMOTE_DB),
        ("DATABASE_URL", _REMOTE_REDIS, _LOOPBACK_DB),
    ],
)
def test_one_misconfigured_url_is_reported_without_the_other(
    variable: str, redis_url: str, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half-configured is the common case and the confusing one.

    Naming both variables when only one is wrong sends whoever reads it to check
    something that is already correct.
    """
    _settings(
        monkeypatch,
        environment="production",
        redis_url=redis_url,
        database_url=database_url,
    )

    with pytest.raises(RuntimeError) as raised:
        check_backing_services()

    message = str(raised.value)
    assert variable in message
    other = "DATABASE_URL" if variable == "REDIS_URL" else "REDIS_URL"
    assert other not in message


def test_the_message_never_carries_the_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection string carries a password, and a boot failure is a widely-read log.

    The guard reports the *variable name* and the environment, both of which are safe,
    and never the value — which is the whole reason it matches on the parsed host rather
    than formatting the URL into the message.
    """
    _settings(
        monkeypatch,
        environment="production",
        redis_url="redis://default:hunter2@localhost:6379/0",
    )

    with pytest.raises(RuntimeError) as raised:
        check_backing_services()

    assert "hunter2" not in str(raised.value)
    assert "redis://" not in str(raised.value)


@pytest.mark.parametrize("environment", sorted(LOCAL_ENVIRONMENTS))
def test_local_development_still_boots_against_localhost(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defaults exist so `just up` needs no configuration. That must keep working."""
    _settings(monkeypatch, environment=environment, redis_url=_LOOPBACK_REDIS)

    check_backing_services()


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0", "[::1]"])
def test_loopback_is_recognised_however_it_is_spelled(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`localhost` is the default, but a hand-set URL can name the same place directly.

    Catching only the literal string would make the guard a check on one spelling of the
    mistake rather than on the mistake.
    """
    _settings(
        monkeypatch,
        environment="production",
        redis_url=f"redis://{host}:6379/0",
        # Correct, so the raise can only be about the host spelling under test.
        database_url=_REMOTE_DB,
    )

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        check_backing_services()


def test_a_properly_configured_deployment_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shape that actually runs on Railway, so the guard is not merely always-red."""
    _settings(
        monkeypatch,
        environment="production",
        redis_url="redis://default:pw@redis.railway.internal:6379/0",
        database_url="postgresql://user:pw@postgres.railway.internal:5432/railway",
    )

    check_backing_services()


def test_the_worker_dies_rather_than_retrying_an_unreachable_broker() -> None:
    """The guard that needs no variable to be right.

    `check_backing_services` above is silent when `ENVIRONMENT` is itself unset, which is
    exactly the state the incident was in. This setting is what covers it: Celery exits
    instead of retrying, the restart policy crash-loops the service, and the failure is
    visible without reading a log.
    """
    from worker.celery_app import celery_app

    assert celery_app.conf.broker_connection_retry_on_startup is False
    # Steady-state reconnection is a different question and stays on: a broker that
    # vanishes mid-life is a transient dependency, and every consumer is idempotent so
    # picking back up is safe.
    assert celery_app.conf.broker_connection_retry is True


@pytest.mark.parametrize(
    "url",
    [
        # NFKC-fragile characters in the password and in the host. `urlsplit` raises
        # `ValueError` on both, with the netloc — password included — in the message.
        "postgresql://citizenship:s℀cret@db.internal:5432/app",
        "postgresql://citizenship:pw@db℀.internal:5432/app",
    ],
)
def test_an_unparseable_url_never_reaches_the_traceback(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must not become the leak it exists to avoid.

    `urlsplit` validates the netloc under NFKC and raises with the netloc inlined. Left
    uncaught, a password containing one such character would be printed into a crash
    trace on a platform log — a worse disclosure than the misconfiguration the guard was
    written to report, and from the same line.
    """
    _settings(monkeypatch, environment="production", database_url=url, redis_url=_REMOTE_REDIS)

    # Either outcome is acceptable; quoting the URL is not. The point is that nothing
    # propagates out of here carrying the credential.
    try:
        check_backing_services()
    except RuntimeError as exc:
        assert "cret" not in str(exc)
        assert url not in str(exc)
