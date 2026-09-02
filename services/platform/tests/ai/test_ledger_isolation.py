"""The spend survives the caller's rollback, and the caller's work survives the spend.

Every other test in this package binds the ledger to the test's own session so it can
read what was written. That is convenient and it hides the property this file exists
for: in production `invoke` opens its **own** session, and the separation is what
makes the ceiling trustworthy.

The defect this guards against is specific and was in the first draft. `invoke` used
to commit the *caller's* session. Two consequences, one of which is a silent hole in
the ceiling:

- a task that called the model and then failed would roll back the cost along with
  its own work, so a document failing repeatedly would be billed repeatedly and
  counted zero times — invisible to the exact runaway the ceiling exists to stop;
- and, in slice 2's worker, committing the caller's session mid-task would publish
  half-written domain rows at the moment a model was called.

These tests use real, separate connections, so they assert the behaviour rather than
the arrangement.
"""

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text

from app.ai.domain import Capability, ModelRun
from app.ai.fake import FakeProvider, succeeded
from app.ai.provider import DocumentText
from app.ai.service import AiBudget, invoke
from app.core.config import Settings
from app.shared.db import get_sessionmaker

pytestmark = pytest.mark.integration


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


def _settings() -> Settings:
    return Settings(
        environment="test",
        ai_provider="fake",
        ai_request_timeout_seconds=5.0,
        ai_task_deadline_seconds=30.0,
        ai_daily_spend_ceiling_usd=1.0,
    )


def test_the_cost_is_durable_even_when_the_caller_rolls_back() -> None:
    """The money was spent. A ledger that forgets it because the caller's work failed
    is a ledger that under-reports precisely the failing loop it should be stopping."""
    caller = get_sessionmaker()()
    try:
        # The caller has uncommitted work of its own in flight.
        caller.execute(text("SELECT 1"))

        invoke(
            FakeProvider(responses=[succeeded(_Out(status="ready"))]),
            capability=Capability.PROVIDER_PROBE,
            document=DocumentText("ping"),
            output_schema=_Out,
            budget=AiBudget(seconds=30.0),
            settings=_settings(),
        )
        caller.rollback()
    finally:
        caller.close()

    # A third connection: if the run were only visible inside the caller's aborted
    # transaction, this would find nothing.
    with get_sessionmaker()() as observer:
        runs = list(observer.execute(select(ModelRun)).scalars())
    assert len(runs) == 1
    assert runs[0].estimated_cost_usd > 0


def test_invoke_does_not_commit_the_callers_session() -> None:
    """The half that bites in slice 2. A model call must not publish whatever else the
    caller happens to have in flight."""
    caller = get_sessionmaker()()
    try:
        caller.execute(text("CREATE TEMP TABLE caller_work (id int)"))
        caller.execute(text("INSERT INTO caller_work VALUES (1)"))
        in_transaction_before = caller.in_transaction()

        invoke(
            FakeProvider(responses=[succeeded(_Out(status="ready"))]),
            capability=Capability.PROVIDER_PROBE,
            document=DocumentText("ping"),
            output_schema=_Out,
            budget=AiBudget(seconds=30.0),
            settings=_settings(),
        )

        assert in_transaction_before and caller.in_transaction(), (
            "the caller's transaction was closed by a model call"
        )
        # And it is still *uncommitted*: rolling back must still discard the work.
        caller.rollback()
        remaining = caller.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_name='caller_work'")
        ).scalar_one()
    finally:
        caller.close()

    assert remaining == 0, "the caller's work was committed by a model call"


def test_invoke_takes_no_caller_session_at_all() -> None:
    """Structural, and the reason the two behaviours above cannot regress quietly:
    `invoke` has no parameter through which a caller's session could be passed, so
    committing one is not something a future edit can do by accident."""
    import inspect

    parameters = inspect.signature(invoke).parameters
    assert "session" not in parameters
    annotations = {name: str(p.annotation) for name, p in parameters.items()}
    assert not any(a == "Session" for a in annotations.values()), (
        f"`invoke` gained a Session parameter: {annotations}"
    )
