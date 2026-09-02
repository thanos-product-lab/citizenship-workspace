"""The ceiling, the ledger, and the task deadline.

The controls moved forward from M11 (IMPLEMENTATION_ROADMAP §1, change 8) because
the first live model call is when runaway cost becomes possible.

Two of these tests assert things that are easy to get subtly wrong and impossible to
notice in production until the bill arrives: that a *failed* call still costs, and
that the ceiling refuses before dialling rather than after.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import spend
from app.ai.domain import AiDailySpend, Capability, ModelRun, ModelRunStatus
from app.ai.fake import FakeProvider, failed, succeeded
from app.ai.provider import DocumentText
from app.ai.service import AiBudget, AiDeadlineExceeded, invoke
from app.ai.spend import SpendCeilingReached
from app.core.config import Settings

pytestmark = pytest.mark.integration


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


def _invoke(
    provider: FakeProvider,
    settings: Settings,
    ledger: Callable[[], Session],
    *,
    budget_seconds: float | None = None,
) -> object:
    return invoke(
        provider,
        capability=Capability.PROVIDER_PROBE,
        document=DocumentText("ping"),
        output_schema=_Out,
        budget=AiBudget(seconds=budget_seconds or settings.ai_task_deadline_seconds),
        settings=settings,
        sessionmaker=ledger,
        trace_id="trace-1",
    )


def _runs(session: Session) -> list[ModelRun]:
    return list(session.execute(select(ModelRun)).scalars())


# --- the ledger ------------------------------------------------------------------


def test_a_successful_call_is_recorded_and_costs(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    provider = FakeProvider(responses=[succeeded(_Out(status="ready"))])
    result = _invoke(provider, ai_settings, ledger)

    (run,) = _runs(db_session)
    assert run.status == ModelRunStatus.SUCCEEDED.value
    assert run.capability == Capability.PROVIDER_PROBE.value
    assert run.prompt_version == "provider_probe.v1"
    assert run.schema_version == "probe.v1"
    assert run.trace_id == "trace-1"
    assert run.output_hash is not None
    assert run.estimated_cost_usd > 0
    assert result.model_run_id == run.id  # type: ignore[attr-defined]

    assert spend.spent_today(db_session, at=datetime.now(UTC)) == pytest.approx(
        float(run.estimated_cost_usd)
    )


def test_a_failed_call_still_costs(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    """The one that would silently break the ceiling.

    A provider bills for the tokens it processed whether or not the output validated,
    so a ledger counting only successes would under-report exactly the runaway the
    ceiling exists to stop — a loop of schema-invalid retries, each billed, none
    counted.
    """
    provider = FakeProvider(
        responses=[
            failed(ModelRunStatus.INVALID_OUTPUT, input_tokens=900, output_tokens=50, attempts=3)
        ]
    )
    _invoke(provider, ai_settings, ledger)

    (run,) = _runs(db_session)
    assert run.status == ModelRunStatus.INVALID_OUTPUT.value
    assert run.attempts == 3
    assert run.estimated_cost_usd > 0, "a failed call that consumed tokens must be charged"
    assert spend.spent_today(db_session, at=datetime.now(UTC)) > 0


def test_the_ledger_accumulates_across_calls(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    provider = FakeProvider(
        responses=[succeeded(_Out(status="ready")), succeeded(_Out(status="ready"))]
    )
    _invoke(provider, ai_settings, ledger)
    first = spend.spent_today(db_session, at=datetime.now(UTC))
    _invoke(provider, ai_settings, ledger)
    second = spend.spent_today(db_session, at=datetime.now(UTC))

    assert second > first
    row = db_session.get(AiDailySpend, datetime.now(UTC).date())
    assert row is not None and row.calls == 2


def test_the_ledger_is_keyed_on_the_utc_day(db_session: Session) -> None:
    """A ceiling that resets at local midnight resets at a different instant depending
    on what the process thinks its timezone is."""
    at = datetime(2026, 9, 2, 23, 30, tzinfo=UTC)
    spend.record(db_session, at=at, cost_usd=0.01)
    spend.record(db_session, at=at + timedelta(hours=1), cost_usd=0.01)  # next UTC day
    db_session.flush()

    days = sorted(d for (d,) in db_session.execute(select(AiDailySpend.day)).all())
    assert len(days) == 2, "the boundary must fall at 00:00 UTC"


# --- the ceiling -----------------------------------------------------------------


def test_the_ceiling_refuses_before_dialling(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    """A hard stop, and — the part that matters — one that costs nothing to enforce.
    A ceiling checked after the call would be a report, not a limit."""
    spend.record(db_session, at=datetime.now(UTC), cost_usd=ai_settings.ai_daily_spend_ceiling_usd)
    db_session.flush()

    provider = FakeProvider(responses=[succeeded(_Out(status="ready"))])
    with pytest.raises(SpendCeilingReached) as caught:
        _invoke(provider, ai_settings, ledger)

    assert provider.calls == [], "the provider must not be reached once the ceiling is met"
    assert caught.value.ceiling_usd == ai_settings.ai_daily_spend_ceiling_usd
    assert "Resets at 00:00 UTC" in str(caught.value)


def test_a_refused_call_is_still_recorded(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    """A `model_runs` table holding only the calls we managed to make cannot answer
    "why did nothing happen yesterday"."""
    spend.record(db_session, at=datetime.now(UTC), cost_usd=ai_settings.ai_daily_spend_ceiling_usd)
    db_session.flush()

    with pytest.raises(SpendCeilingReached):
        _invoke(FakeProvider(responses=[]), ai_settings, ledger)

    (run,) = _runs(db_session)
    assert run.status == ModelRunStatus.SPEND_CEILING_REACHED.value
    assert run.estimated_cost_usd == Decimal(0)
    assert run.attempts == 0, "nothing was attempted"


def test_the_ceiling_is_deployment_wide_not_per_tenant(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    """`ai_daily_spend` has one row per day and no tenant column, which is what makes
    the ceiling a bound on the *bill* rather than on any one user's usage."""
    assert "case_id" not in {c.name for c in AiDailySpend.__table__.columns}
    assert [c.name for c in AiDailySpend.__table__.primary_key] == ["day"]


def test_the_ceiling_reads_committed_totals_under_a_lock() -> None:
    """`record` is a read-modify-write, so it must take the row lock. Asserted on the
    statement rather than by racing two connections: a timing test that passes by
    luck is worse than none, and the property is structural."""
    import inspect

    source = inspect.getsource(spend._lock_day)
    assert "with_for_update()" in source


# --- the task deadline -----------------------------------------------------------


def test_the_budget_refuses_a_call_it_cannot_fit(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    """The bound a per-request timeout does not give you.

    Compared against the *next call's* timeout rather than against zero: with a
    remaining-greater-than-zero test, a task with two seconds left would start a call
    permitted fifteen and blow the deadline it was meant to protect.
    """
    provider = FakeProvider(responses=[succeeded(_Out(status="ready"))])
    # A budget smaller than one request's timeout can never fit a call.
    with pytest.raises(AiDeadlineExceeded) as caught:
        _invoke(provider, ai_settings, ledger, budget_seconds=1.0)

    assert provider.calls == [], "the deadline must be checked before dialling"
    assert "cannot accommodate" in str(caught.value)


def test_the_budget_is_checked_before_the_ceiling(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    """If there is no time to make the call, there is no point asking whether we can
    afford it — and no `SPEND_CEILING_REACHED` row should be written for a call that
    was never going to happen."""
    spend.record(db_session, at=datetime.now(UTC), cost_usd=ai_settings.ai_daily_spend_ceiling_usd)
    db_session.flush()

    with pytest.raises(AiDeadlineExceeded):
        _invoke(FakeProvider(responses=[]), ai_settings, ledger, budget_seconds=0.5)

    assert _runs(db_session) == []


def test_a_budget_with_room_permits_the_call(
    db_session: Session, ledger: Callable[[], Session], ai_settings: Settings
) -> None:
    provider = FakeProvider(responses=[succeeded(_Out(status="ready"))])
    _invoke(provider, ai_settings, ledger, budget_seconds=30.0)
    assert len(provider.calls) == 1


def test_the_budget_shrinks_as_calls_are_made(ai_settings: Settings) -> None:
    budget = AiBudget(seconds=10.0)
    first = budget.remaining
    budget.started -= 6.0  # simulate six seconds of calls
    assert budget.remaining < first
    # 4s left cannot accommodate a 5s call.
    with pytest.raises(AiDeadlineExceeded):
        budget.check(next_call_timeout=ai_settings.ai_request_timeout_seconds)
