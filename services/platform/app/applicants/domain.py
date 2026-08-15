"""RouteProfile aggregate, RouteProfileVersion, their enums, and the draft event.

The draft model (approved in the M2 plan; RFC §9):

- A RouteProfile has exactly one **DRAFT** RouteProfileVersion during onboarding,
  edited **in place** (`version_number` stays 1, no version proliferation). The
  DRAFT is the only mutable version.
- Confirming (a later slice) appends an immutable **CONFIRMED** version; §9.4's
  immutability binds CONFIRMED versions only, never the working draft.

Draft answers structurally live on the *version* (RFC §9.1), but the
optimistic-concurrency token lives on the *profile* (`revision`). So a draft edit
must advance the profile's revision even though the mutated columns are on the
child row — see `RouteProfileService.save_draft`, which flags the profile modified
to make `version_id_col` engage on every save.
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


class StatusType(StrEnum):
    ILR = "ILR"
    ILE = "ILE"
    EU_SETTLED_STATUS = "EU_SETTLED_STATUS"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ReviewState(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class RouteProfile(Base):
    __tablename__ = "route_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), unique=True, index=True)
    # App-maintained pointer to the current version. Kept as a plain column (not a
    # DB FK) to avoid a circular constraint with route_profile_versions.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    # SQLAlchemy optimistic concurrency; a stale revision raises StaleDataError.
    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012

    @classmethod
    def start(cls, *, case_id: uuid.UUID) -> "RouteProfile":
        return cls(id=uuid.uuid4(), case_id=case_id, revision=1)


class RouteProfileVersion(Base):
    __tablename__ = "route_profile_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    route_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_profiles.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    # All answer fields are nullable: a draft is a partially-filled form. Completeness
    # is enforced at CONFIRM time (a later slice), not during capture.
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    status_type: Mapped[str | None] = mapped_column(String(20))
    status_granted_on: Mapped[date | None] = mapped_column(Date)
    married_to_british_citizen: Mapped[bool | None] = mapped_column(Boolean)
    may_already_be_british: Mapped[bool | None] = mapped_column(Boolean)
    review_state: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # App-maintained pointer to the version this one supersedes (null for a draft).
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column()

    @classmethod
    def new_draft(
        cls,
        *,
        route_profile_id: uuid.UUID,
        created_by: str,
        version_number: int = 1,
        supersedes_version_id: uuid.UUID | None = None,
    ) -> "RouteProfileVersion":
        return cls(
            id=uuid.uuid4(),
            route_profile_id=route_profile_id,
            version_number=version_number,
            review_state=ReviewState.DRAFT.value,
            created_by=created_by,
            supersedes_version_id=supersedes_version_id,
        )

    def confirmed_copy(self, *, created_by: str) -> "RouteProfileVersion":
        """Snapshot this draft as a new immutable CONFIRMED version (§9.4: confirming
        creates a version, never an update; CONFIRMED versions are immutable)."""
        return RouteProfileVersion(
            id=uuid.uuid4(),
            route_profile_id=self.route_profile_id,
            version_number=self.version_number + 1,
            date_of_birth=self.date_of_birth,
            status_type=self.status_type,
            status_granted_on=self.status_granted_on,
            married_to_british_citizen=self.married_to_british_citizen,
            may_already_be_british=self.may_already_be_british,
            review_state=ReviewState.CONFIRMED.value,
            created_by=created_by,
            supersedes_version_id=self.id,
        )

    @property
    def answered_fields(self) -> list[str]:
        """Which answers are present — used for a non-identifying event payload."""
        present = {
            "date_of_birth": self.date_of_birth is not None,
            "status_type": self.status_type is not None,
            "status_granted_on": self.status_granted_on is not None,
            "married_to_british_citizen": self.married_to_british_citizen is not None,
            "may_already_be_british": self.may_already_be_british is not None,
        }
        return sorted(key for key, ok in present.items() if ok)


@dataclass(frozen=True)
class RouteProfileDraftSaved(DomainEvent):
    version_number: int
    answered_fields: tuple[str, ...]

    aggregate_type: ClassVar[str] = "RouteProfile"
    event_type: ClassVar[str] = "RouteProfileDraftSaved"

    def payload(self) -> dict[str, Any]:
        # §38.1: identifiers + which fields are answered, never the answer *values*
        # (date of birth and status type are sensitive and stay out of the event).
        return {
            "route_profile_id": str(self.aggregate_id),
            "version_number": self.version_number,
            "answered_fields": list(self.answered_fields),
        }


@dataclass(frozen=True)
class RouteProfileConfirmed(DomainEvent):
    version_number: int
    version_id: str

    aggregate_type: ClassVar[str] = "RouteProfile"
    event_type: ClassVar[str] = "RouteProfileConfirmed"

    def payload(self) -> dict[str, Any]:
        # Identifiers only; the confirmed answers stay in the version row, not here.
        return {
            "route_profile_id": str(self.aggregate_id),
            "version_number": self.version_number,
            "version_id": self.version_id,
        }
