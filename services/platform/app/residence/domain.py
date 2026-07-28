"""ProposedApplicationDate aggregate, its immutable versions, enums, and events.

The versioning model (Domain §10, and the append-always decision agreed for M3A):

- A case has one current ProposedApplicationDate *root*; selecting a different date
  appends a new immutable CONFIRMED version to that root (the date evolves) and emits
  `ProposedApplicationDateChanged`. The schema leaves room for additional candidate
  roots (`is_current` distinguishes them) so M3B date comparison needs no migration,
  but M3A only ever creates one root per case.
- Unlike M2's route-profile draft, there is **no edit-in-place**: every selection is
  a discrete user action, so each appends a version and *no version ever mutates*.
  That literal immutability is what M3B's stale-propagation and history views rely on.

As in 0003, `current_version_id` and `supersedes_version_id` are app-maintained UUID
pointers (no circular / self FK); the optimistic-concurrency token (`revision`) lives
on the root even though the values live on the child version — so a selection must
flag the root modified to make `version_id_col` engage (see `service._advance_root`).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.messaging import DomainEvent


class DateReviewState(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class DateSource(StrEnum):
    # A user-entered selection (M3A) vs a date the presence rule suggests (M3B).
    USER_ENTERED = "USER_ENTERED"
    SYSTEM_SUGGESTED = "SYSTEM_SUGGESTED"


class ProposedApplicationDate(Base):
    __tablename__ = "proposed_application_dates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    # App-maintained pointer to the current version (plain column: avoids a circular
    # FK with the version table, matching the 0003 route-profile convention).
    current_version_id: Mapped[uuid.UUID | None] = mapped_column()
    # Mirrors the case's authoritative `current_proposed_application_date_id` pointer
    # (Domain §10.3). A partial unique index enforces at most one current per case.
    is_current: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012

    @classmethod
    def start(cls, *, case_id: uuid.UUID) -> "ProposedApplicationDate":
        return cls(id=uuid.uuid4(), case_id=case_id, is_current=True, revision=1)


class ProposedApplicationDateVersion(Base):
    __tablename__ = "proposed_application_date_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proposed_application_date_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposed_application_dates.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    # Stored as a calendar DATE with no timezone (Domain §6.2, RULES_SPEC §4): the
    # M3B +1-day window is derived from this raw value, never pre-computed here.
    application_date: Mapped[date] = mapped_column(Date)
    review_state: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column()

    @classmethod
    def new_confirmed(
        cls,
        *,
        proposed_application_date_id: uuid.UUID,
        application_date: date,
        created_by: str,
        version_number: int,
        source: DateSource = DateSource.USER_ENTERED,
        supersedes_version_id: uuid.UUID | None = None,
    ) -> "ProposedApplicationDateVersion":
        """A selected date is a CONFIRMED, immutable version. M3A only writes
        USER_ENTERED; SYSTEM_SUGGESTED arrives with the M3B presence-resolving date."""
        return cls(
            id=uuid.uuid4(),
            proposed_application_date_id=proposed_application_date_id,
            version_number=version_number,
            application_date=application_date,
            review_state=DateReviewState.CONFIRMED.value,
            source=source.value,
            created_by=created_by,
            supersedes_version_id=supersedes_version_id,
        )


@dataclass(frozen=True)
class ProposedApplicationDateSelected(DomainEvent):
    """A case's first proposed application date. The date is a planning intention,
    not sensitive identity data, so it is carried for self-contained provenance
    (ADR-0004), unlike the answer values kept out of the route-profile events."""

    version_number: int
    application_date: str
    source: str

    aggregate_type: ClassVar[str] = "ProposedApplicationDate"
    event_type: ClassVar[str] = "ProposedApplicationDateSelected"

    def payload(self) -> dict[str, Any]:
        return {
            "proposed_application_date_id": str(self.aggregate_id),
            "version_number": self.version_number,
            "application_date": self.application_date,
            "source": self.source,
        }


@dataclass(frozen=True)
class ProposedApplicationDateChanged(DomainEvent):
    """The current proposed date was changed to a new value (a new immutable version
    on the same root). In M3B this is a stale-propagation trigger; in M3A it is the
    write-command that M3B will hook, left deliberately without propagation now."""

    version_number: int
    application_date: str
    source: str

    aggregate_type: ClassVar[str] = "ProposedApplicationDate"
    event_type: ClassVar[str] = "ProposedApplicationDateChanged"

    def payload(self) -> dict[str, Any]:
        return {
            "proposed_application_date_id": str(self.aggregate_id),
            "version_number": self.version_number,
            "application_date": self.application_date,
            "source": self.source,
        }
