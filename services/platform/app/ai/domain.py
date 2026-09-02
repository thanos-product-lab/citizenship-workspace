"""What a model invocation leaves behind, and the ledger that bounds the spending.

Two tables, both deliberately outside the tenant.

**`ModelRun` has no `case_id`, and that is the design.** Technical Architecture RFC
§20 asks for a record of *every model invocation*; RFC §8's `ExtractionRun` (M8
slice 2) is the case-scoped domain record of "capability X ran against evidence
file Y". They are different things and the difference matters: a single extraction
run that retries twice makes three invocations, and the ceiling has to see all
three. So `ExtractionRun` will carry `case_id` and reference the `ModelRun` rows it
produced, while this table stays global infrastructure telemetry.

Keeping the case off it buys three properties at once. It has no tenant dimension,
so RLS on it would be wrong rather than missing. It needs no handling in the
case-deletion path (Domain §51.1), which is correct for a row that by construction
holds nothing about a person. And the spend ledger it feeds is a deployment-wide
number, which is what a spend ceiling has to be.

**There is no column here that a prompt, a document, or a model payload could be
written into.** That is the privacy guarantee (Architecture §20: *"Do not store
sensitive document content in telemetry"*), and it is structural rather than a
redaction step someone has to remember: `output_hash` is a digest, `capability` and
the version fields are enum-like identifiers, and the rest are integers. A future
change that adds a `payload` column has to argue with this docstring and with
`tests/ai/test_model_run_shape.py`.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Capability(StrEnum):
    """The narrow capabilities of Architecture RFC §19.

    `PROVIDER_PROBE` is not one of them and is not a product capability: it is the
    fixed, tiny call `/health/ai-probe` makes so the deployed smoke can tell a
    working key from a well-formed one. It appears here because it is a real model
    invocation and §20 says *every* invocation gets a record — including the one we
    make on purpose to check the wiring, whose cost is as real as any other.
    """

    PROVIDER_PROBE = "PROVIDER_PROBE"
    DOCUMENT_CLASSIFIER = "DocumentClassifier"
    DOCUMENT_CLAIM_EXTRACTOR = "DocumentClaimExtractor"
    TRAVEL_RECORD_EXTRACTOR = "TravelRecordExtractor"


class ModelRunStatus(StrEnum):
    """How an invocation ended. Every one of these is a *verdict* — there is no
    value meaning "we gave up without deciding", because that state is what the
    task deadline and the attempt cap exist to prevent."""

    #: Structured output came back and validated.
    SUCCEEDED = "SUCCEEDED"
    #: The provider declined. Recoverable, and never a fabricated fallback
    #: (AI_EVALUATION_PLAN §8.14).
    REFUSED = "REFUSED"
    #: Output did not satisfy the schema on any attempt. No claim is created.
    INVALID_OUTPUT = "INVALID_OUTPUT"
    #: The provider errored in a way more attempts could have fixed, and the cap ran out.
    FAILED = "FAILED"
    #: The provider errored in a way no retry could fix — an exhausted credit
    #: balance, a rejected key. Distinct from FAILED because retrying it is the
    #: defect the spike found (AI_SPIKE_FINDINGS §5).
    TERMINAL = "TERMINAL"
    #: One call exceeded `ai_request_timeout_seconds`.
    TIMED_OUT = "TIMED_OUT"
    #: Refused before dialling, because the day's ceiling was already reached.
    SPEND_CEILING_REACHED = "SPEND_CEILING_REACHED"


#: Statuses in which no usable output exists. The single definition of "this
#: invocation produced nothing", so a caller cannot decide it differently.
UNPRODUCTIVE_STATUSES = frozenset(ModelRunStatus) - {ModelRunStatus.SUCCEEDED}


class ModelRun(Base):
    """One invocation of one capability against one provider. One row per *attempt
    sequence* — the retries are counted in `attempts`, not spread over rows, because
    the thing worth asking later is "what did this cost and how did it end", and a
    row per HTTP request would make every such question a GROUP BY."""

    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    capability: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(60))
    schema_version: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), index=True)

    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    #: USD. `Numeric`/`Decimal` rather than float, and typed as `Decimal` because that
    #: is what the driver returns: this column is summed into a ledger a ceiling reads,
    #: and binary floating point accumulating a few thousand small costs is a rounding
    #: argument nobody should have to have. Annotating it `float` would have made every
    #: read a silent lie that mypy could not see through.
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal(0))
    attempts: Mapped[int] = mapped_column(Integer, default=1)

    #: Ties an invocation to the request or task that caused it, without naming the
    #: case. This is the join a support question actually uses.
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    #: SHA-256 of the serialised structured output. Lets two runs be compared for
    #: identical output without keeping the output.
    output_hash: Mapped[str | None] = mapped_column(String(64))
    #: The provider's error class name, never its message: a provider message can
    #: quote the request, and the request contains the document.
    failure_class: Mapped[str | None] = mapped_column(String(80))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @classmethod
    def record(
        cls,
        *,
        capability: Capability,
        provider: str,
        model: str,
        prompt_version: str,
        schema_version: str,
        status: ModelRunStatus,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        attempts: int = 1,
        trace_id: str | None = None,
        output_hash: str | None = None,
        failure_class: str | None = None,
    ) -> "ModelRun":
        return cls(
            capability=capability.value,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            schema_version=schema_version,
            status=status.value,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            # One conversion, at the one place a cost enters the table.
            estimated_cost_usd=Decimal(str(estimated_cost_usd)),
            attempts=attempts,
            trace_id=trace_id,
            output_hash=output_hash,
            failure_class=failure_class,
        )


class AiDailySpend(Base):
    """The ledger the ceiling reads: one row per UTC day, deployment-wide.

    A row rather than a `SUM(estimated_cost_usd)` over `model_runs`, for two
    reasons. It is a lockable object — `SELECT ... FOR UPDATE` on one row is what
    stops two workers reading the same total and each writing it back as if the
    other had not spent. And it stays correct if `model_runs` is ever pruned for
    retention, which a running total over a table that might be trimmed would not.

    **UTC, deliberately.** A ceiling that resets at local midnight resets at a
    different instant depending on where the process thinks it is, and the failure
    is a doubled budget on the day the clocks change.
    """

    __tablename__ = "ai_daily_spend"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal(0))
    calls: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
