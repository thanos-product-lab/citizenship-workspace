"""Boundary schemas for selecting a proposed application date.

A proposed application date is a forward-looking planning intention, so there is no
future/past constraint here (a Pydantic `date` already rejects a malformed value).
Domain validity — e.g. a date earlier than the status-holding period allows — is an
M3B rules concern, deliberately not enforced at this input boundary.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.residence.domain import (
    DateConfidence,
    ProposedApplicationDate,
    ProposedApplicationDateVersion,
    TravelRecord,
    TravelRecordVersion,
    TravelReviewState,
)


class SelectApplicationDateInput(BaseModel):
    application_date: date
    # Optimistic-concurrency token: the root revision the client last saw. Omitted on
    # the first selection (no root exists yet); required to change an existing date.
    expected_revision: int | None = None


class ProposedApplicationDateResponse(BaseModel):
    case_id: uuid.UUID
    application_date: date
    version_number: int
    review_state: str
    source: str
    is_current: bool
    revision: int
    created_at: datetime

    @classmethod
    def from_domain(
        cls, root: ProposedApplicationDate, version: ProposedApplicationDateVersion
    ) -> "ProposedApplicationDateResponse":
        return cls(
            case_id=root.case_id,
            application_date=version.application_date,
            version_number=version.version_number,
            review_state=version.review_state,
            source=version.source,
            is_current=root.is_current,
            revision=root.revision,
            created_at=root.created_at,
        )


class TravelRecordInput(BaseModel):
    """A manual travel entry. `date_confidence` and `review_state` are independent
    (§11.4, §11.5) and default to EXACT/CONFIRMED — a user entering a trip is asserting
    it — but can be downgraded to make an uncertain record visibly distinct."""

    destination_label: str = Field(min_length=1, max_length=120)
    departure_date: date
    return_date: date
    date_confidence: DateConfidence = DateConfidence.EXACT
    review_state: TravelReviewState = TravelReviewState.CONFIRMED
    destination_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    notes: str | None = None

    @field_validator("destination_country_code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def _departure_not_after_return(self) -> "TravelRecordInput":
        # Rejected at the boundary (→ 422), never persisted (RULES_SPEC §7.8). Equal is
        # allowed: a same-day trip is zero absent days. The DB CHECK backs this up.
        if self.departure_date > self.return_date:
            raise ValueError("departure_date cannot be after return_date")
        return self


class TravelRecordEditInput(TravelRecordInput):
    # Optimistic-concurrency token: the record revision the client last saw.
    expected_revision: int | None = None


class TravelRecordResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    version_number: int
    destination_label: str
    destination_country_code: str | None
    departure_date: date
    return_date: date
    date_confidence: str
    review_state: str
    entry_source: str
    notes: str | None
    lifecycle_status: str
    revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls, record: TravelRecord, version: TravelRecordVersion
    ) -> "TravelRecordResponse":
        return cls(
            id=record.id,
            case_id=record.case_id,
            version_number=version.version_number,
            destination_label=version.destination_label,
            destination_country_code=version.destination_country_code,
            departure_date=version.departure_date,
            return_date=version.return_date,
            date_confidence=version.date_confidence,
            review_state=version.review_state,
            entry_source=version.entry_source,
            notes=version.notes,
            lifecycle_status=record.lifecycle_status.value,
            revision=record.revision,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
