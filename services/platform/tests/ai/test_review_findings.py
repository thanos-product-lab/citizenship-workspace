"""Regression tests for what the slice-1 reviews found.

Each of these was a real defect in the first version of this module, found by review
rather than by a test — which is the argument for writing the test now: a defect
found once and fixed without a test is a defect waiting for the next refactor.
"""

import inspect
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import boot, config, provider, service
from app.ai.domain import Capability, ModelRun, ModelRunStatus
from app.ai.fake import FakeProvider
from app.ai.prompts import PromptVersion, SystemPrompt
from app.ai.provider import DocumentText, ModelConfig, OpenAIProvider
from app.ai.service import AiBudget, invoke
from app.core.config import Settings
from app.main import app

pytestmark = pytest.mark.integration


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


# --- the spend is recorded even when the call does not return normally ------------


class _Exploding:
    """A provider that dies after the request would have been billed."""

    name = "exploding"

    def generate_structured(self, **_: Any) -> Any:
        raise RuntimeError("provider died after the request was sent")


def test_a_provider_that_raises_still_writes_a_run_and_moves_the_ledger(
    db_session: Session, ledger: Any, ai_settings: Settings
) -> None:
    """Both reviews converged on this. Anything raising between the provider call and
    the ledger write — a malformed response, a hard time limit, a pod eviction — lost
    the cost permanently, and the retry then spent it again. A ledger that
    under-counts exactly the failing loop it exists to bound is worse than none,
    because the number it reports looks reassuring.
    """
    with pytest.raises(RuntimeError):
        invoke(
            _Exploding(),
            capability=Capability.PROVIDER_PROBE,
            document=DocumentText("ping"),
            output_schema=_Out,
            budget=AiBudget(seconds=30.0),
            settings=ai_settings,
            sessionmaker=ledger,
        )

    (run,) = list(db_session.execute(select(ModelRun)).scalars())
    assert run.failure_class == "UnrecordedProviderFailure"
    assert run.status == ModelRunStatus.FAILED.value


def test_celerys_soft_time_limit_is_never_swallowed_by_the_retry_loop() -> None:
    """`SoftTimeLimitExceeded` derives from `Exception`, so the broad handler caught
    Celery's own deadline, called it a retryable fault, and issued up to two more
    real billable calls after the task had been told to stop — then died to the hard
    limit before any of them could be recorded.

    `evidence/extraction.py` documents the identical bug from M7. This is the same
    mistake in a new module.
    """
    from celery.exceptions import SoftTimeLimitExceeded

    requests: list[dict[str, Any]] = []

    class _Client:
        def __init__(self) -> None:
            self.chat = self
            self.completions = self

        def parse(self, **kwargs: Any) -> Any:
            requests.append(kwargs)
            raise SoftTimeLimitExceeded()

    with pytest.raises(SoftTimeLimitExceeded):
        OpenAIProvider(_Client()).generate_structured(
            capability=Capability.PROVIDER_PROBE,
            system=SystemPrompt(PromptVersion.PROVIDER_PROBE_V1),
            document=DocumentText("ping"),
            output_schema=_Out,
            config=ModelConfig(model="gpt-4o-mini", timeout_seconds=5, max_attempts=3),
        )

    assert len(requests) == 1, "the task's own deadline must not buy two more calls"


def test_a_response_with_no_choices_is_a_verdict_not_an_escape() -> None:
    """`completion.choices[0]` sat outside the try, so a malformed response raised
    `IndexError` straight out of the adapter, past every recording path — billed and
    invisible."""

    class _Empty:
        def __init__(self) -> None:
            self.usage = type("U", (), {"prompt_tokens": 50, "completion_tokens": 0})()
            self.choices: list[Any] = []

    class _Client:
        def __init__(self) -> None:
            self.chat = self
            self.completions = self

        def parse(self, **_: Any) -> Any:
            return _Empty()

    result = OpenAIProvider(_Client()).generate_structured(
        capability=Capability.PROVIDER_PROBE,
        system=SystemPrompt(PromptVersion.PROVIDER_PROBE_V1),
        document=DocumentText("ping"),
        output_schema=_Out,
        config=ModelConfig(model="gpt-4o-mini", timeout_seconds=5, max_attempts=2),
    )
    assert result.status is ModelRunStatus.INVALID_OUTPUT
    assert result.input_tokens == 100, "tokens the provider billed for must still count"


# --- the probe's gate --------------------------------------------------------------


def test_a_non_ascii_probe_secret_is_rejected_not_a_500() -> None:
    """`secrets.compare_digest` raises `TypeError` on non-ASCII `str`, and Starlette
    decodes headers as latin-1 — so one 0xFF byte was an unauthenticated 500. Worse
    than noise: a *disabled* probe 404s before the comparison, so the 500 told an
    anonymous caller that AI_PROBE_SECRET is set, which is exactly what returning 404
    rather than 403 exists to hide.
    """
    settings = Settings(environment="test", ai_provider="fake", ai_probe_secret="x" * 40)
    from app.core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    try:
        # Sent as raw bytes, which is what a real client puts on the wire. The test
        # client refuses a non-ASCII `str` outright, so passing one would have proved
        # nothing about the server — Starlette decodes the header as latin-1 and hands
        # the handler a `str` containing \xff, which is what reached compare_digest.
        response = TestClient(app).post(
            "/health/ai-probe", headers={b"X-Probe-Secret": b"\xff\xfe"}
        )
        assert response.status_code == 403, (
            f"non-ASCII secret produced {response.status_code}; a 500 here is an "
            "unauthenticated crash and an oracle for whether the probe is enabled"
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_the_probe_is_absent_from_the_published_schema() -> None:
    """The 404 hides whether the probe is *enabled*. A route listing in
    `/openapi.json` gives away that it exists at all, for free."""
    assert "/health/ai-probe" not in app.openapi()["paths"]


def test_a_short_probe_secret_is_refused_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probe spends against the same ledger as extraction, and nothing in the
    application rate-limits — so a guessed secret does not waste a few dollars, it
    exhausts the day's ceiling and stops every user's processing until 00:00 UTC."""
    monkeypatch.setattr(
        boot,
        "get_settings",
        lambda: Settings(environment="local", ai_provider="fake", ai_probe_secret="short"),
    )
    with pytest.raises(RuntimeError, match="AI_PROBE_SECRET"):
        boot.check_ai_configuration()


# --- fail-open paths in the controls themselves ------------------------------------


def test_an_unpriced_model_is_refused_rather_than_costing_nothing() -> None:
    """`_PRICES.get(model, (0.0, 0.0))` meant a capability registered with a new model
    computed a cost of zero on every call, so the ledger never rose and the ceiling
    could never be reached — a fail-open inside the one control that bounds the bill,
    triggered by the ordinary act of adding a capability."""
    unpriced = config.CapabilityConfig(
        capability=Capability.DOCUMENT_CLASSIFIER,
        model="some-model-nobody-priced",
        prompt_version=PromptVersion.PROVIDER_PROBE_V1,
        schema_version="v1",
    )
    with pytest.raises(RuntimeError, match="_PRICES"):
        unpriced.model_config_with(Settings())


def test_the_worker_validates_the_ai_configuration_too() -> None:
    """The guard ran only in `create_app`, so a worker deployed with no key — or with
    `AI_PROVIDER=fake` — booted perfectly clean. From slice 2 the worker is where
    every real model call lives."""
    source = inspect.getsource(__import__("worker.celery_app", fromlist=["celery_app"]))
    assert "check_ai_configuration()" in source


def test_the_fake_provider_still_validates_the_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """`just up` runs on the fake, so an early return there meant the deadline
    arithmetic was never checked in the environment developers actually use — and a
    broken deadline would first be discovered on a deployment."""
    monkeypatch.setattr(
        boot,
        "get_settings",
        lambda: Settings(
            environment="local",
            ai_provider="fake",
            ai_request_timeout_seconds=90.0,
            ai_task_deadline_seconds=45.0,
        ),
    )
    with pytest.raises(RuntimeError, match="AI_REQUEST_TIMEOUT_SECONDS"):
        boot.check_ai_configuration()


# --- claims that were stated rather than enforced -----------------------------------


def test_invoke_is_the_only_route_to_a_provider() -> None:
    """`service.py` claims it is "the only way to reach a provider". It was a claim:
    `factory.get_provider()` and `config.config_for()` are both public, so bypassing
    the ceiling, the deadline and the `ModelRun` was three lines of ordinary-looking
    code. Now it is checked."""
    import pathlib

    app_dir = pathlib.Path(service.__file__).parent.parent
    allowed = {"ai/service.py", "ai/provider.py", "ai/fake.py"}
    offenders = [
        f"{path.relative_to(app_dir)}:{number}"
        for path in app_dir.rglob("*.py")
        if str(path.relative_to(app_dir)) not in allowed
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if ".generate_structured(" in line
    ]
    assert offenders == [], (
        f"a provider is called outside ai/service.py: {offenders}. Every model call must "
        "go through `invoke`, which owns the spend ceiling, the task deadline and the "
        "ModelRun record."
    )


def test_a_provider_must_declare_its_name() -> None:
    """`getattr(provider, "name", "unknown")` meant a provider that forgot its name
    silently recorded runs attributed to nobody, in a provenance column."""
    assert "name" in provider.AIProvider.__annotations__
    assert FakeProvider().name == "fake"
    assert OpenAIProvider(object()).name == "openai"


def test_an_over_long_trace_id_cannot_break_the_post_call_ledger_write(
    db_session: Session, ledger: Any, ai_settings: Settings
) -> None:
    """`TraceIdMiddleware` accepts an unvalidated caller-supplied `x-request-id`, and
    the column is `String(64)`. Combined with the unrecorded-spend bug above, an
    over-long header was a way to make a call that never reached the ledger."""
    from app.ai.fake import succeeded

    invoke(
        FakeProvider(responses=[succeeded(_Out(status="ready"))]),
        capability=Capability.PROVIDER_PROBE,
        document=DocumentText("ping"),
        output_schema=_Out,
        budget=AiBudget(seconds=30.0),
        trace_id="x" * 500,
        settings=ai_settings,
        sessionmaker=ledger,
    )

    (run,) = list(db_session.execute(select(ModelRun)).scalars())
    assert run.trace_id is not None and len(run.trace_id) == 64


def test_the_call_has_an_explicit_output_ceiling() -> None:
    """`spend.py` bounds the overshoot by "concurrency x cost-per-call". That is only
    as true as the per-call bound, which was inherited from undocumented provider
    defaults until it was stated here."""
    assert ModelConfig(model="m", timeout_seconds=1, max_attempts=1).max_output_tokens > 0
    source = inspect.getsource(OpenAIProvider.generate_structured)
    assert "max_completion_tokens=config.max_output_tokens" in source
