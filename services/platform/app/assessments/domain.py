"""The immutable assessment graph: runs, results, and input links.

Three insert-only aggregates that record *what was concluded, from which exact inputs,
under which rule version* — the product's provenance backbone (Domain §29-31). Nothing
here is edited in place:

- An `AssessmentRun` is one evaluation execution.
- An `AssessmentResult` is a per-requirement conclusion. It never changes conclusion
  after creation; recalculation writes a **new** result and marks the previous one
  SUPERSEDED. A partial unique index (migration 0007) enforces at most one CURRENT
  result per case + requirement.
- An `AssessmentInputLink` records one versioned input a result read. The set of links on
  a result must equal the rule's declared dependencies (strict provenance).

Conclusion and currency are two independent axes (ADR-0001): `conclusion` is what we
concluded; `currency` is whether that conclusion is still current. They are stored as
separate columns and never collapsed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.requirements.domain import Currency
from app.shared.db import Base
from app.shared.messaging import DomainEvent


class AssessmentMode(StrEnum):
    TRUSTED = "TRUSTED"
    PROVISIONAL = "PROVISIONAL"


class AssessmentRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RecalculationFailureCode(StrEnum):
    """Why a run failed, as a **code**. Stored in `AssessmentRun.failure_summary`.

    That column is `Text`, and the obvious thing to put in it is `str(exc)`. Never do
    that. A SQLAlchemy error carries the statement's bound parameters, so an exception
    string is the shortest path from a destination label or a date of birth into a
    database column nothing treats as case data — the leak §11 forbids in logs, through a
    door nobody was watching.

    Two codes, because they call for different responses and nothing finer is knowable
    without inspecting the exception: a packaging bug an engineer must fix, and everything
    else, which a retry may well clear.
    """

    #: A catalogued requirement has no definition row or no active rule version. The
    #: deployment is inconsistent; retrying will fail the same way.
    RULE_CONFIGURATION_INVALID = "RULE_CONFIGURATION_INVALID"
    #: Anything else — a lost connection, a serialisation failure, an evaluator defect.
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class AssessmentTriggerType(StrEnum):
    CASE_CREATED = "CASE_CREATED"
    ROUTE_CONFIRMED = "ROUTE_CONFIRMED"
    APPLICATION_DATE_CHANGED = "APPLICATION_DATE_CHANGED"
    TRAVEL_RECORD_CHANGED = "TRAVEL_RECORD_CHANGED"
    FACT_CHANGED = "FACT_CHANGED"
    EVIDENCE_SUPPORT_CHANGED = "EVIDENCE_SUPPORT_CHANGED"
    RULE_VERSION_CHANGED = "RULE_VERSION_CHANGED"
    USER_REQUESTED = "USER_REQUESTED"
    SYSTEM_RETRY = "SYSTEM_RETRY"


class AssessmentRun(Base):
    __tablename__ = "assessment_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(40))
    trigger_event_id: Mapped[uuid.UUID | None] = mapped_column()
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    rule_set_hash: Mapped[str | None] = mapped_column(String(64))
    input_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initiated_by: Mapped[str] = mapped_column(String(255))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    failure_summary: Mapped[str | None] = mapped_column(Text)

    @classmethod
    def start(
        cls,
        *,
        case_id: uuid.UUID,
        trigger_type: AssessmentTriggerType,
        mode: AssessmentMode,
        initiated_by: str,
    ) -> "AssessmentRun":
        return cls(
            id=uuid.uuid4(),
            case_id=case_id,
            trigger_type=trigger_type.value,
            mode=mode.value,
            status=AssessmentRunStatus.RUNNING.value,
            initiated_by=initiated_by,
        )

    def complete(self, *, at: datetime) -> None:
        self.status = AssessmentRunStatus.COMPLETED.value
        self.completed_at = at

    def fail(
        self, *, code: RecalculationFailureCode, at: datetime, trace_id: str | None = None
    ) -> None:
        """The run produced no results (Domain §41.4). The row exists so the failure
        survives the page reload that erases a transient banner — without it a failed
        recalculation leaves stale results and nothing at all saying why they were not
        refreshed.

        `failure_summary` takes the code and only the code; the exception itself is
        re-raised to the caller and logged, never persisted (see `RecalculationFailureCode`).
        `trace_id` is what ties this row to that log line.
        """
        self.status = AssessmentRunStatus.FAILED.value
        self.completed_at = at
        self.failure_summary = code.value
        self.trace_id = trace_id


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_runs.id"))
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement_definitions.id"))
    rule_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_versions.id"))
    conclusion: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(20))
    summary_code: Mapped[str | None] = mapped_column(String(60))
    summary_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    calculation_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Structured child values (Domain §33-34): typed {code, severity, parameters} objects,
    # never prose. Default to empty lists (added in migration 0008).
    limitations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    next_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    input_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    marked_stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_reason_code: Mapped[str | None] = mapped_column(String(60))
    superseded_by_result_id: Mapped[uuid.UUID | None] = mapped_column()

    @classmethod
    def new_current(
        cls,
        *,
        result_id: uuid.UUID,
        run_id: uuid.UUID,
        case_id: uuid.UUID,
        requirement_id: uuid.UUID,
        rule_version_id: uuid.UUID,
        conclusion: str,
        summary_code: str | None,
        summary_parameters: dict[str, Any],
        calculation_breakdown: dict[str, Any],
        limitations: list[dict[str, Any]] | None = None,
        next_actions: list[dict[str, Any]] | None = None,
    ) -> "AssessmentResult":
        """A freshly evaluated trusted result. Created CURRENT; the caller supersedes any
        prior current result for the same case + requirement first."""
        return cls(
            id=result_id,
            assessment_run_id=run_id,
            case_id=case_id,
            requirement_id=requirement_id,
            rule_version_id=rule_version_id,
            conclusion=conclusion,
            currency=Currency.CURRENT.value,
            summary_code=summary_code,
            summary_parameters=summary_parameters,
            calculation_breakdown=calculation_breakdown,
            limitations=limitations or [],
            next_actions=next_actions or [],
        )

    def supersede(self, *, by_result_id: uuid.UUID) -> None:
        """CURRENT/STALE → SUPERSEDED, pointing at the result that replaces it. A conclusion
        is never edited; supersession only changes currency and the forward pointer."""
        self.currency = Currency.SUPERSEDED.value
        self.superseded_by_result_id = by_result_id

    def mark_stale(self, *, reason_code: str, at: datetime) -> None:
        """CURRENT → STALE: the conclusion still stands but an input changed under it, so it
        must be recalculated. Conclusion is untouched (conclusion ⟂ currency, ADR-0001); only
        an already-superseded result is refused, since staling it would rewrite history."""
        if self.currency == Currency.SUPERSEDED.value:
            raise ValueError("cannot mark a superseded result stale")
        self.currency = Currency.STALE.value
        self.marked_stale_at = at
        self.stale_reason_code = reason_code


class AssessmentInputLink(Base):
    __tablename__ = "assessment_input_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assessment_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessment_results.id"))
    input_kind: Mapped[str] = mapped_column(String(40))
    input_version_id: Mapped[uuid.UUID] = mapped_column()
    input_key: Mapped[str | None] = mapped_column(String(60))
    contribution_role: Mapped[str] = mapped_column(String(20))
    snapshot_value_hash: Mapped[str | None] = mapped_column(String(64))


@dataclass(frozen=True)
class AssessmentRunCompleted(DomainEvent):
    """A trusted assessment run finished and wrote current results. Structural only
    (§38.1): counts and mode, never a conclusion or any personal data."""

    trigger_type: str
    mode: str
    result_count: int

    aggregate_type: ClassVar[str] = "AssessmentRun"
    event_type: ClassVar[str] = "AssessmentRunCompleted"

    def payload(self) -> dict[str, Any]:
        return {
            "assessment_run_id": str(self.aggregate_id),
            "trigger_type": self.trigger_type,
            "mode": self.mode,
            "result_count": self.result_count,
        }


@dataclass(frozen=True)
class AssessmentRunFailed(DomainEvent):
    """A trusted run was attempted and wrote no results (Domain §38, §41.4).

    Structural only (§38.1): the trigger, the mode, and the failure *code*. Never the
    exception, which is the one thing here that could carry case data — see
    `RecalculationFailureCode`.

    Emitted on the recovery transaction, not the failed one: the failed transaction is
    rolled back by definition, so an event emitted inside it would vanish with everything
    else and the log would show a recalculation that was never attempted.
    """

    trigger_type: str
    mode: str
    failure_code: str

    aggregate_type: ClassVar[str] = "AssessmentRun"
    event_type: ClassVar[str] = "AssessmentRunFailed"

    def payload(self) -> dict[str, Any]:
        return {
            "assessment_run_id": str(self.aggregate_id),
            "trigger_type": self.trigger_type,
            "mode": self.mode,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True)
class AssessmentInvalidated(DomainEvent):
    """Current results were marked STALE because an input changed under them (Domain §41.2).

    Structural only (§38.1): the reason code, which requirements were affected, and how many
    results. Requirement keys are stable public identifiers from the catalog, not case data,
    so naming them carries no personal information — and without them the event records that
    *something* went stale while a consumer auditing selective invalidation cannot tell what.
    Never a conclusion.
    """

    reason_code: str
    affected_count: int
    requirement_keys: tuple[str, ...] = ()

    aggregate_type: ClassVar[str] = "ApplicationCase"
    event_type: ClassVar[str] = "AssessmentInvalidated"

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": str(self.aggregate_id),
            "reason_code": self.reason_code,
            "affected_count": self.affected_count,
            "requirement_keys": list(self.requirement_keys),
        }
