"""ApplicationCase aggregate, CaseMembership, their enums, and case events.

Two design choices worth reading closely:

1. **Lifecycle is a guarded state machine, not a settable column.** `lifecycle_status`
   is exposed read-only; the private column mutates *only* through the transition
   methods (`activate`, `request_deletion`). So `ACTIVE` has exactly one code path
   into it — `activate()` — whose sole caller is the route-support decision that
   lands in a later slice. There is no way to type `case.lifecycle_status = ACTIVE`.

2. **`revision` is the optimistic-concurrency version column** (Domain §6.4). A
   command carrying a stale revision fails on flush rather than overwriting a
   concurrent change.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.errors import IllegalTransition
from app.shared.messaging import DomainEvent


class LifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"


class SupportStatus(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class CasePhase(StrEnum):
    SETTING_UP = "SETTING_UP"
    BUILDING_CASE = "BUILDING_CASE"
    RESOLVING_ISSUES = "RESOLVING_ISSUES"
    NEARLY_PREPARED = "NEARLY_PREPARED"
    FINAL_REVIEW = "FINAL_REVIEW"


class RouteKey(StrEnum):
    SECTION_6_1_STANDARD = "SECTION_6_1_STANDARD"


class MembershipRole(StrEnum):
    OWNER = "OWNER"


class ApplicationCase(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(200))
    route_key: Mapped[str] = mapped_column(String(40))
    # Private column: the state machine below is the only writer.
    _lifecycle_status: Mapped[str] = mapped_column("lifecycle_status", String(20))
    _support_status: Mapped[str] = mapped_column("support_status", String(20))
    current_phase: Mapped[str] = mapped_column(String(20))
    # Set in M3A; nullable now so the column exists from Migration 1 (Domain §55).
    current_proposed_application_date_id: Mapped[uuid.UUID | None] = mapped_column()
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    # SQLAlchemy requires this exact class-level dict; the version column drives
    # optimistic concurrency. (RUF012 wants ClassVar, but that clashes with the
    # base's declaration under mypy — SQLAlchemy's own convention wins.)
    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012

    @classmethod
    def create(cls, *, owner_user_id: str, title: str) -> "ApplicationCase":
        """A new case always starts as a DRAFT, single supported route, unevaluated."""
        return cls(
            id=uuid.uuid4(),
            owner_user_id=owner_user_id,
            title=title,
            route_key=RouteKey.SECTION_6_1_STANDARD.value,
            _lifecycle_status=LifecycleStatus.DRAFT.value,
            _support_status=SupportStatus.NOT_EVALUATED.value,
            current_phase=CasePhase.SETTING_UP.value,
            revision=1,
        )

    @property
    def lifecycle_status(self) -> LifecycleStatus:
        return LifecycleStatus(self._lifecycle_status)

    @property
    def support_status(self) -> SupportStatus:
        return SupportStatus(self._support_status)

    def activate(self) -> None:
        """DRAFT → ACTIVE. The only path to ACTIVE; caller is the support decision.

        A case may only become assessable once onboarding resolves to a supported
        route, so activation is refused from any state but DRAFT."""
        if self.lifecycle_status is not LifecycleStatus.DRAFT:
            raise IllegalTransition(
                f"cannot activate a case in {self.lifecycle_status} state"
            )
        self._lifecycle_status = LifecycleStatus.ACTIVE.value

    def request_deletion(self, *, at: datetime) -> None:
        """→ DELETION_PENDING. Blocks further writes; terminal states cannot re-enter."""
        if self.lifecycle_status in (LifecycleStatus.DELETION_PENDING, LifecycleStatus.DELETED):
            raise IllegalTransition(
                f"cannot request deletion of a case in {self.lifecycle_status} state"
            )
        self._lifecycle_status = LifecycleStatus.DELETION_PENDING.value
        self.deletion_requested_at = at

    def record_route_support(self, support: "SupportStatus") -> None:
        """Record the route-support outcome and, if supported, activate the case.

        This is the *only* caller of `activate()`: a case becomes assessable only
        when onboarding resolves to a supported route. A non-supported outcome sets
        the status and leaves the case in DRAFT so onboarding can be revised."""
        self._support_status = support.value
        if support is SupportStatus.SUPPORTED:
            self.activate()


class CaseMembership(Base):
    __tablename__ = "case_memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_membership_case_user"),)

    @classmethod
    def owner(cls, *, case_id: uuid.UUID, user_id: str) -> "CaseMembership":
        return cls(
            id=uuid.uuid4(),
            case_id=case_id,
            user_id=user_id,
            role=MembershipRole.OWNER.value,
        )


@dataclass(frozen=True)
class CaseCreated(DomainEvent):
    route_key: str

    aggregate_type: ClassVar[str] = "ApplicationCase"
    event_type: ClassVar[str] = "CaseCreated"

    def payload(self) -> dict[str, Any]:
        # Narrow, non-identifying fields only (§38.1): no title, no user free text.
        return {"case_id": str(self.aggregate_id), "route_key": self.route_key}


@dataclass(frozen=True)
class CaseDeletionRequested(DomainEvent):
    """Deletion requested; the case is now DELETION_PENDING and blocks writes. The
    outbox twin queues the eventual purge of case-scoped records and stored files."""

    aggregate_type: ClassVar[str] = "ApplicationCase"
    event_type: ClassVar[str] = "CaseDeletionRequested"

    def payload(self) -> dict[str, Any]:
        return {"case_id": str(self.aggregate_id)}


@dataclass(frozen=True)
class RouteSupportEvaluated(DomainEvent):
    """The route-support decision recorded against a case. Carries the conclusions,
    summary code, and rule-set version so the outcome is reproducible without any
    persisted assessment result (ADR-0004) — and no answer values (§38.1)."""

    support_status: str
    composite_conclusion: str
    adult_conclusion: str
    status_conclusion: str
    summary_code: str | None
    route_profile_version_id: str
    reference_date: str
    rule_set: str
    semantic_version: str

    aggregate_type: ClassVar[str] = "ApplicationCase"
    event_type: ClassVar[str] = "RouteSupportEvaluated"

    def payload(self) -> dict[str, Any]:
        # Self-contained provenance (ADR-0004): the exact input version evaluated
        # and the reference date used, so the decision is reproducible from this
        # one event without correlating others.
        return {
            "case_id": str(self.aggregate_id),
            "support_status": self.support_status,
            "composite_conclusion": self.composite_conclusion,
            "adult_conclusion": self.adult_conclusion,
            "status_conclusion": self.status_conclusion,
            "summary_code": self.summary_code,
            "route_profile_version_id": self.route_profile_version_id,
            "reference_date": self.reference_date,
            "rule_set": self.rule_set,
            "semantic_version": self.semantic_version,
        }
