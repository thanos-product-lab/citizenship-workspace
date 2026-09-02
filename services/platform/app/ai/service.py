"""The only way to reach a provider, and the reason there is only one.

Every model invocation in the system goes through `invoke`. Not by convention —
`provider.py` deliberately does not know about the ledger and the ledger does not
know about the provider, so a caller wanting to skip the accounting would have to
assemble a provider, a config and a client itself, which is a diff that looks exactly
like what it is.

`invoke` owns three things a provider adapter must not:

1. **Affordability.** A ceiling check before the call, the actual cost after —
   including after a failure, because a provider bills for tokens it processed
   whether or not the output validated.
2. **The task deadline.** `AiBudget` bounds the *sequence* of calls one task makes.
   A per-request timeout bounds one call; Celery kills the task, and M8 makes two
   calls per document.
3. **The `ModelRun` record.** Architecture §20's every-invocation rule, written on
   every path including the refused, the timed out, and the never-dialled — a ledger
   with a hole where the failures were is not a ledger.

**The ledger runs in its own session, in short transactions of its own.** Three
reasons, and the third is the one that makes it necessary rather than tidy:

- The money is spent whether or not the caller's work succeeds. A ledger that rolled
  back with the caller would forget the cost of a task that failed after calling the
  model — so a document failing repeatedly would be billed repeatedly and counted
  zero times, which is the exact runaway the ceiling exists to stop, made invisible
  to it.
- The row lock is released promptly instead of being held for whatever else the
  caller's transaction is doing, which would serialise every model call in the
  deployment behind one row.
- Committing the *caller's* session would commit the caller's partial work. The
  first draft did this, and in slice 2's worker — which runs the pipeline inside one
  transaction — it would have committed half-written domain rows at the moment a
  model was called. Nothing about "record the spend" implies "publish the caller's
  unfinished state", and coupling them was a defect waiting for the slice that has
  more than one row in flight.
"""

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.config import config_for
from app.ai.domain import Capability, ModelRun, ModelRunStatus, utcnow
from app.ai.prompts import SystemPrompt
from app.ai.provider import AIProvider, DocumentText, ProviderResult
from app.ai.spend import SpendCeilingReached, record, reserve
from app.core.config import Settings, get_settings
from app.shared.db import get_sessionmaker

_log = structlog.get_logger()

#: How the ledger gets a session. Injectable so a test can bind it to the same
#: transaction its assertions read from.
LedgerSession = Callable[[], Session]


class AiDeadlineExceeded(Exception):
    """The task's total AI budget is spent. Terminal for the task, not just the call.

    Distinct from a per-request timeout: that one call may have been fine, and the
    point is that there is no time left to make another before Celery's soft limit
    arrives. Raised *before* dialling, so it costs nothing.
    """


@dataclass
class AiBudget:
    """Wall-clock budget for all the model calls one task may make.

    The same two-bounds shape `evidence/extraction.py` argues for, and for the same
    reason: an output bound limits how much comes back, a *work* bound limits what it
    costs to get, and only the second stops a task being killed by something that
    cannot report why.

    Checked *between* calls rather than inside one — a call already in flight is
    bounded by its own timeout, and interrupting it would abandon a request the
    provider will bill for anyway.
    """

    seconds: float
    started: float = field(default_factory=time.monotonic)

    @property
    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.started)

    def check(self, *, next_call_timeout: float) -> None:
        """Raise if the next call could outlive the budget.

        Compares against the *next call's* timeout rather than against zero, which is
        the difference between a budget and a wish: with `remaining > 0` a task with
        two seconds left would start a call permitted fifteen, and the deadline would
        be exceeded by the one call it was supposed to prevent.
        """
        if self.remaining < next_call_timeout:
            raise AiDeadlineExceeded(
                f"AI task budget of {self.seconds:.0f}s has {max(self.remaining, 0):.1f}s left, "
                f"which cannot accommodate a call permitted {next_call_timeout:.0f}s"
            )


@dataclass(frozen=True)
class Invocation:
    """What `invoke` produced: the parsed output if there is one, and the id of the
    `ModelRun` that recorded it. Callers store the id for provenance; slice 2's
    `ExtractionRun` references it."""

    status: ModelRunStatus
    parsed: BaseModel | None
    model_run_id: uuid.UUID
    latency_ms: int
    attempts: int

    @property
    def succeeded(self) -> bool:
        return self.status is ModelRunStatus.SUCCEEDED


@contextmanager
def _ledger(sessionmaker: LedgerSession | None) -> Iterator[Session]:
    """A short transaction of the ledger's own, committed on the way out."""
    session = (sessionmaker or get_sessionmaker())()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def invoke(
    provider: AIProvider,
    *,
    capability: Capability,
    document: DocumentText,
    output_schema: type[BaseModel],
    budget: AiBudget,
    trace_id: str | None = None,
    settings: Settings | None = None,
    sessionmaker: LedgerSession | None = None,
) -> Invocation:
    """Make one capability call, bounded and accounted for.

    Takes no caller session, by design — see the module docstring. Raises
    `SpendCeilingReached` and `AiDeadlineExceeded` rather than returning them as a
    status, because both are conditions the caller's work must stop for rather than
    results to inspect, and a status can be ignored. Both still write a `ModelRun`,
    so a refusal to dial is as visible in the record as a failure after dialling.
    """
    settings = settings or get_settings()
    capability_config = config_for(capability)
    model_config = capability_config.model_config_with(settings)
    system = SystemPrompt(capability_config.prompt_version)

    def _run(status: ModelRunStatus, **kwargs: object) -> ModelRun:
        return ModelRun.record(
            capability=capability,
            provider=getattr(provider, "name", "unknown"),
            model=capability_config.model,
            prompt_version=capability_config.prompt_version.value,
            schema_version=capability_config.schema_version,
            status=status,
            trace_id=trace_id,
            **kwargs,  # type: ignore[arg-type]
        )

    # Costs nothing and happens before anything else: if there is no time to make the
    # call, there is no point checking whether we can afford it.
    budget.check(next_call_timeout=model_config.timeout_seconds)

    # Transaction one: can we afford it? The lock is taken and released here rather
    # than held across the provider call, which would serialise every model call in
    # the deployment. What that costs is a bounded overshoot — see `spend.py`.
    with _ledger(sessionmaker) as session:
        try:
            reserve(session, at=utcnow(), ceiling_usd=settings.ai_daily_spend_ceiling_usd)
        except SpendCeilingReached:
            # Recorded, not just raised. A `model_runs` table holding only the calls
            # we managed to make cannot answer "why did nothing happen yesterday".
            session.add(
                _run(
                    ModelRunStatus.SPEND_CEILING_REACHED,
                    latency_ms=0,
                    attempts=0,
                    failure_class="SpendCeilingReached",
                )
            )
            # Committed by the context manager on the way out of the `raise`? No —
            # it rolls back on an exception, which would discard the record along
            # with it. Commit the record explicitly first.
            session.commit()
            raise

    result: ProviderResult = provider.generate_structured(
        capability=capability,
        system=system,
        document=document,
        output_schema=output_schema,
        config=model_config,
    )

    cost = model_config.cost_usd(
        input_tokens=result.input_tokens, output_tokens=result.output_tokens
    )

    # Transaction two: what did it cost, and how did it end.
    with _ledger(sessionmaker) as session:
        run = _run(
            result.status,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=cost,
            attempts=result.attempts,
            output_hash=result.output_hash,
            failure_class=result.failure_class,
        )
        session.add(run)
        session.flush()
        run_id = run.id
        total = record(session, at=utcnow(), cost_usd=cost)

    _log.info(
        "ai.invoked",
        capability=capability.value,
        status=result.status.value,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost_usd=round(cost, 8),
        day_total_usd=round(total, 8),
        trace_id=trace_id,
    )
    return Invocation(
        status=result.status,
        parsed=result.parsed,
        model_run_id=run_id,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
    )
