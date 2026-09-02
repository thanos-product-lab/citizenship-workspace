"""The local-green/deployed-red guards.

M7 hit that pattern five times, and a model provider is its purest form: credentials
plus network plus quota, trivially faked on a laptop. It is also worse than the Redis
case, because a missing key crashes nothing — it just makes every document fail at
the extraction stage while the API keeps reporting itself ready.

The tests are split by what they can actually prove. Everything here is about
*configuration presence*; whether the key is accepted is what `/health/ai-probe` and
the deployed smoke are for, and no unit test can stand in for that.
"""

from collections.abc import Iterator

import pytest

from app.ai import boot
from app.core.config import Settings
from app.core.config import get_settings as real_get_settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "production",
        "ai_provider": "openai",
        "openai_api_key": "sk-test",
        "ai_daily_spend_ceiling_usd": 5.0,
        "ai_request_timeout_seconds": 15.0,
        "ai_task_deadline_seconds": 45.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _isolated_settings() -> Iterator[None]:
    """`get_settings` is `lru_cache`d, so a value another test built must not leak in.

    Cleared on `app.core.config.get_settings` rather than on `boot.get_settings`: the
    tests below monkeypatch the latter to a lambda, and by teardown that lambda is
    what the name refers to — which has no `cache_clear` and turned every test in this
    file into a teardown error.
    """
    real_get_settings.cache_clear()
    yield
    real_get_settings.cache_clear()


def _with(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr(boot, "get_settings", lambda: settings)


def test_a_deployment_without_a_key_refuses_to_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, _settings(openai_api_key=""))
    with pytest.raises(RuntimeError) as caught:
        boot.check_ai_configuration()

    message = str(caught.value)
    assert "OPENAI_API_KEY" in message
    # Naming what was observed is the whole diagnostic value: a bare "must be set"
    # cannot distinguish never-set from set-on-the-wrong-service from not-redeployed.
    assert "ENVIRONMENT='production'" in message
    assert "sk-" not in message, "a boot error must never quote the value"


def test_local_development_without_a_key_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app must import without secrets — tests, OpenAPI export, CI."""
    _with(monkeypatch, _settings(environment="local", openai_api_key=""))
    boot.check_ai_configuration()


def test_the_fake_provider_cannot_be_selected_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dangerous misconfiguration. The fake returns schema-valid synthetic output,
    so a deployment running on it would present fabricated values as model proposals
    and nothing downstream could tell."""
    _with(monkeypatch, _settings(ai_provider="fake"))
    with pytest.raises(RuntimeError) as caught:
        boot.check_ai_configuration()
    assert "AI_PROVIDER=fake" in str(caught.value)


def test_the_fake_provider_is_allowed_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, _settings(environment="local", ai_provider="fake"))
    boot.check_ai_configuration()


@pytest.mark.parametrize("ceiling", [0.0, -1.0])
def test_a_non_positive_ceiling_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch, ceiling: float
) -> None:
    """Zero refuses every call and negative is a mistake being read as a budget.
    Both are the environment variable having failed to arrive, which is the M7
    pattern again — a plausible-looking default standing in for a missing value."""
    _with(monkeypatch, _settings(ai_daily_spend_ceiling_usd=ceiling))
    with pytest.raises(RuntimeError, match="AI_DAILY_SPEND_CEILING_USD"):
        boot.check_ai_configuration()


def test_a_request_timeout_larger_than_the_task_deadline_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Easy to break from either side, and the symptom is a worker killed mid-write by
    Celery's soft limit — which reports nothing about either setting."""
    _with(monkeypatch, _settings(ai_request_timeout_seconds=60.0, ai_task_deadline_seconds=45.0))
    with pytest.raises(RuntimeError, match="AI_REQUEST_TIMEOUT_SECONDS"):
        boot.check_ai_configuration()


def test_the_deadline_fits_inside_celerys_soft_limit() -> None:
    """The arithmetic the whole two-bounds design rests on (AI_SPIKE_FINDINGS §4).

    Asserted against the real Celery setting rather than a copy of the number, so
    raising the soft limit without revisiting the budget cannot pass quietly.
    """
    from worker.celery_app import celery_app

    settings = Settings()
    soft_limit = celery_app.conf.task_soft_time_limit
    assert settings.ai_task_deadline_seconds < soft_limit, (
        f"AI task deadline {settings.ai_task_deadline_seconds}s must leave headroom under "
        f"Celery's soft limit of {soft_limit}s, or the task is killed by a bound that "
        "cannot report why"
    )
    # Two calls per document (classify, then extract) is what M8 actually does.
    assert settings.ai_request_timeout_seconds * 2 <= settings.ai_task_deadline_seconds


def test_readiness_reports_configuration_not_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ai_configured` must not make a call — an orchestrator polls readiness every few
    seconds, and a live model call there would bill the account for uptime."""
    import inspect

    source = inspect.getsource(boot.ai_configured)
    assert "invoke" not in source and "generate_structured" not in source

    _with(monkeypatch, _settings(openai_api_key="sk-test"))
    assert boot.ai_configured() is True
    _with(monkeypatch, _settings(openai_api_key=""))
    assert boot.ai_configured() is False
