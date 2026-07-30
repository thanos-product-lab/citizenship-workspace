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

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.errors import IllegalTransition
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


# --- TravelRecord ----------------------------------------------------------


class TravelLifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"


class DateConfidence(StrEnum):
    # Independent of review_state: a record can be CONFIRMED yet ESTIMATED. Both must
    # hold (CONFIRMED + EXACT) for M3B to admit a record to a trusted total (§6.1).
    EXACT = "EXACT"
    ESTIMATED = "ESTIMATED"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class TravelReviewState(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    UNCERTAIN = "UNCERTAIN"


class EntrySource(StrEnum):
    MANUAL = "MANUAL"
    CSV_IMPORT = "CSV_IMPORT"
    CONFIRMED_CLAIM = "CONFIRMED_CLAIM"
    CORRECTED_CLAIM = "CORRECTED_CLAIM"


# Single source of truth for the destination-label cap, so the manual schema, the CSV
# validator, and the DB column agree (they diverged before: the CSV path skipped the
# check and over-long labels 500'd at the varchar(120) boundary). The migration keeps a
# literal 120 by convention (a snapshot); changing this needs a matching migration.
DESTINATION_LABEL_MAX_LENGTH = 120


class TravelRecord(Base):
    """One reported period outside the UK. The stable identity; the values live on its
    immutable versions. Removal is a tombstone (lifecycle → REMOVED, §11.3), never a
    hard delete — the row and every version stay inspectable."""

    __tablename__ = "travel_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column()
    # Private column: the tombstone transition below is the only writer (mirrors the
    # ApplicationCase lifecycle pattern), so REMOVED has exactly one code path in.
    _lifecycle_status: Mapped[str] = mapped_column("lifecycle_status", String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012

    @classmethod
    def start(cls, *, case_id: uuid.UUID) -> "TravelRecord":
        return cls(
            id=uuid.uuid4(),
            case_id=case_id,
            _lifecycle_status=TravelLifecycleStatus.ACTIVE.value,
            revision=1,
        )

    @property
    def lifecycle_status(self) -> TravelLifecycleStatus:
        return TravelLifecycleStatus(self._lifecycle_status)

    def mark_removed(self) -> None:
        """ACTIVE → REMOVED (a tombstone). Idempotency is refused, not silent: removing
        an already-removed record raises rather than emitting a second removal."""
        if self.lifecycle_status is TravelLifecycleStatus.REMOVED:
            raise IllegalTransition("the travel record is already removed")
        self._lifecycle_status = TravelLifecycleStatus.REMOVED.value


class TravelRecordVersion(Base):
    __tablename__ = "travel_record_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    travel_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("travel_records.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    destination_country_code: Mapped[str | None] = mapped_column(String(2))
    destination_label: Mapped[str] = mapped_column(String(DESTINATION_LABEL_MAX_LENGTH))
    # Raw trip endpoints as calendar DATEs (§6.2). Stored true, never pre-clipped or
    # pre-counted: the M3B rules do endpoint-exclusive counting and window clipping
    # from these values (RULES_SPEC §5). The DB CHECK guards departure <= return.
    departure_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date] = mapped_column(Date)
    date_confidence: Mapped[str] = mapped_column(String(20))
    review_state: Mapped[str] = mapped_column(String(20))
    entry_source: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column()

    @classmethod
    def build(
        cls,
        *,
        travel_record_id: uuid.UUID,
        version_number: int,
        destination_label: str,
        departure_date: date,
        return_date: date,
        date_confidence: DateConfidence,
        review_state: TravelReviewState,
        entry_source: EntrySource,
        created_by: str,
        destination_country_code: str | None = None,
        notes: str | None = None,
        supersedes_version_id: uuid.UUID | None = None,
    ) -> "TravelRecordVersion":
        return cls(
            id=uuid.uuid4(),
            travel_record_id=travel_record_id,
            version_number=version_number,
            destination_country_code=destination_country_code,
            destination_label=destination_label,
            departure_date=departure_date,
            return_date=return_date,
            date_confidence=date_confidence.value,
            review_state=review_state.value,
            entry_source=entry_source.value,
            notes=notes,
            created_by=created_by,
            supersedes_version_id=supersedes_version_id,
        )


@dataclass(frozen=True)
class _TravelEvent(DomainEvent):
    """Shared payload for the travel lifecycle events. Deliberately structural: the
    departure/return dates, destination, and notes are *not* carried — a movement
    timeline is collectively sensitive, and no M3A consumer needs it in the event
    stream (§38.1). The audit entry already records the exact target version id."""

    version_number: int
    date_confidence: str
    review_state: str
    entry_source: str

    def payload(self) -> dict[str, Any]:
        return {
            "travel_record_id": str(self.aggregate_id),
            "version_number": self.version_number,
            "date_confidence": self.date_confidence,
            "review_state": self.review_state,
            "entry_source": self.entry_source,
        }


@dataclass(frozen=True)
class TravelRecordCreated(_TravelEvent):
    aggregate_type: ClassVar[str] = "TravelRecord"
    event_type: ClassVar[str] = "TravelRecordCreated"


@dataclass(frozen=True)
class TravelRecordVersionCreated(_TravelEvent):
    """A new immutable version appended by an edit (the previous version is retained)."""

    aggregate_type: ClassVar[str] = "TravelRecord"
    event_type: ClassVar[str] = "TravelRecordVersionCreated"


@dataclass(frozen=True)
class TravelRecordRemoved(DomainEvent):
    """The record was tombstoned (lifecycle → REMOVED). Versions are untouched."""

    aggregate_type: ClassVar[str] = "TravelRecord"
    event_type: ClassVar[str] = "TravelRecordRemoved"

    def payload(self) -> dict[str, Any]:
        return {"travel_record_id": str(self.aggregate_id)}


@dataclass(frozen=True)
class TravelRecordFields:
    """The full snapshot a create or edit writes into a new immutable version. An edit
    is a whole-version replacement, not a partial patch — a version captures the complete
    state so history stays self-contained. Shared by the manual and CSV-import paths."""

    destination_label: str
    departure_date: date
    return_date: date
    date_confidence: DateConfidence
    review_state: TravelReviewState
    destination_country_code: str | None = None
    notes: str | None = None
