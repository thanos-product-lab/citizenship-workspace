"""The Issue aggregate, its resolutions, enums and events (Domain §36 and §37).

An `Issue` is a durable, user-actionable problem or review item. Two properties shape
everything below.

**An issue never changes an assessment conclusion** (§36.6, CLAUDE.md §2). It is a
*projection* of durable state — results, their limitations, travel records — not a new
fact. Nothing in this module writes an `AssessmentResult`, and no rule reads an issue
(RULES_SPEC §8 was amended to remove the one dependency that did, because issues derive
from results and the reverse edge is a cycle).

**Identity outlives an episode.** The `deduplication_key` names the *cause*, not the
occurrence, so the same cause resolving and returning reuses one row: resolved, then
reopened with `reopened_at` set and its prior `IssueResolution` retained. That is what
makes "did this come back?" answerable.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.messaging import DomainEvent


class IssueType(StrEnum):
    """Domain §36.2 in full. Only `STALE_ASSESSMENT` is derived at this slice; the rest
    arrive with the state that can produce them, and inventing a value outside this list
    requires an RFC change (CLAUDE.md §7)."""

    MISSING_REQUIRED_FACT = "MISSING_REQUIRED_FACT"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    UNCERTAIN_TRAVEL_DATE = "UNCERTAIN_TRAVEL_DATE"
    OVERLAPPING_TRAVEL = "OVERLAPPING_TRAVEL"
    CONFLICTING_CLAIMS = "CONFLICTING_CLAIMS"
    NEAR_THRESHOLD = "NEAR_THRESHOLD"
    STALE_ASSESSMENT = "STALE_ASSESSMENT"
    UNSUPPORTED_COMPLEXITY = "UNSUPPORTED_COMPLEXITY"
    PROCESSING_FAILURE = "PROCESSING_FAILURE"
    #: The same *trip* entered twice (RULES_SPEC §7.8). Distinct from `DUPLICATE_EVIDENCE`
    #: below, which is the same *file* uploaded twice — different cause, different affected
    #: object, different remedy (Domain §36.2).
    DUPLICATE_TRAVEL_RECORD = "DUPLICATE_TRAVEL_RECORD"
    DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class IssueSeverity(StrEnum):
    INFORMATION = "INFORMATION"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKING = "BLOCKING"


class IssueStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class Dismissibility(StrEnum):
    DISMISSIBLE = "DISMISSIBLE"
    NOT_DISMISSIBLE = "NOT_DISMISSIBLE"


class ResolutionType(StrEnum):
    DATA_CORRECTED = "DATA_CORRECTED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    CLAIM_CONFIRMED = "CLAIM_CONFIRMED"
    CLAIM_REJECTED = "CLAIM_REJECTED"
    ASSESSMENT_RECALCULATED = "ASSESSMENT_RECALCULATED"
    USER_DISMISSED = "USER_DISMISSED"
    SYSTEM_AUTO_RESOLVED = "SYSTEM_AUTO_RESOLVED"
    ESCALATED_FOR_REVIEW = "ESCALATED_FOR_REVIEW"


#: Statuses a reconciliation treats as live: the cause is still represented in the queue,
#: so it must not be opened again. DISMISSED is live in this sense — the user has seen it
#: and set it aside — which is why dismissal suppresses recreation but not resolution.
LIVE_STATUSES = (IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value, IssueStatus.DISMISSED.value)


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    issue_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    dismissibility: Mapped[str] = mapped_column(String(20))
    deduplication_key: Mapped[str] = mapped_column(String(200))
    title_code: Mapped[str] = mapped_column(String(60))
    message_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    affected_object_type: Mapped[str] = mapped_column(String(40))
    affected_object_id: Mapped[str] = mapped_column(String(120))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column()
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "severity <> 'BLOCKING' OR dismissibility = 'NOT_DISMISSIBLE'",
            name="ck_issue_blocking_not_dismissible",
        ),
    )
    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012

    @classmethod
    def open_new(
        cls,
        *,
        case_id: uuid.UUID,
        issue_type: IssueType,
        severity: IssueSeverity,
        dismissibility: Dismissibility,
        deduplication_key: str,
        title_code: str,
        affected_object_type: str,
        affected_object_id: str,
        message_parameters: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> "Issue":
        return cls(
            id=uuid.uuid4(),
            case_id=case_id,
            issue_type=issue_type.value,
            severity=severity.value,
            status=IssueStatus.OPEN.value,
            dismissibility=dismissibility.value,
            deduplication_key=deduplication_key,
            title_code=title_code,
            message_parameters=message_parameters or {},
            affected_object_type=affected_object_type,
            affected_object_id=affected_object_id,
            opened_at=at or datetime.now(UTC),
            revision=1,
        )

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    def resolve(self, *, at: datetime) -> None:
        """The cause is gone. Reached from OPEN, IN_PROGRESS **and DISMISSED**.

        Resolving a dismissed issue is the deliberate part. Dismissal is a judgement about
        *this episode* of a cause, not a standing waiver on the cause itself — so when the
        cause disappears the dismissal is spent, and the issue leaves the live set. If it
        did not, a dismissed issue whose cause vanished and later returned would never
        reappear: the reconciler would find a live row and leave it, and the user would be
        told nothing. That silent failure to reopen is the exact defect this milestone
        exists to prevent (ADR-0014, and §6.1 of the M6 plan).
        """
        self.status = IssueStatus.RESOLVED.value
        self.resolved_at = at

    def reopen(self, *, at: datetime) -> None:
        """The cause returned. A new episode on the same row, so the resolution history
        that came before it stays attached and answerable."""
        self.status = IssueStatus.OPEN.value
        self.resolved_at = None
        self.reopened_at = at

    def dismiss(self, *, at: datetime) -> None:
        """Set aside by the user. Callers must check `dismissibility` first — the service
        raises a domain error, and a CHECK constraint stops a BLOCKING issue reaching here
        at all."""
        self.status = IssueStatus.DISMISSED.value
        self.resolved_at = None
        del at


class IssueResolution(Base):
    """Append-only history (§37). A reopened issue keeps every prior row, so "this came
    back" is visible rather than inferred from a status that has since moved on."""

    __tablename__ = "issue_resolutions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id"), index=True)
    resolution_type: Mapped[str] = mapped_column(String(40))
    resolved_by: Mapped[str] = mapped_column(String(255))
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    related_command_id: Mapped[uuid.UUID | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    resulting_object_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)


@dataclass(frozen=True)
class IssuesReconciled(DomainEvent):
    """The open-issue set was recomputed for a case.

    Deduplication keys rather than counts, because "four issues opened" leaves the audit
    trail unable to answer *which* — recoverable only from current table state, which is
    exactly what an append-only log exists not to depend on (§39).

    Structural only (§38.1): a deduplication key is issue type + affected object type +
    an identifier — a requirement key from the catalogue, or an opaque travel-record UUID,
    both of which §38.1 admits. Never a conclusion, a date, a destination label or any
    other case content.

    This replaces §38's per-issue `IssueOpened` / `IssueResolved` / `IssueReopened`, which
    presuppose issues being created one at a time by a handler. Reconciliation moves the
    whole set at once, and one event per pass records that faithfully where three event
    types would imply an ordering that does not exist. See ADR-0015.
    """

    opened: tuple[str, ...] = ()
    resolved: tuple[str, ...] = ()
    reopened: tuple[str, ...] = ()

    aggregate_type: ClassVar[str] = "ApplicationCase"
    event_type: ClassVar[str] = "IssuesReconciled"

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": str(self.aggregate_id),
            "opened": list(self.opened),
            "resolved": list(self.resolved),
            "reopened": list(self.reopened),
        }


@dataclass(frozen=True)
class IssueDismissed(DomainEvent):
    issue_type: str

    aggregate_type: ClassVar[str] = "Issue"
    event_type: ClassVar[str] = "IssueDismissed"

    def payload(self) -> dict[str, Any]:
        return {"issue_id": str(self.aggregate_id), "issue_type": self.issue_type}
