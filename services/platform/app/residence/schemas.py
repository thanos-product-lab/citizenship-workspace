"""Boundary schemas for selecting a proposed application date.

A proposed application date is a forward-looking planning intention, so there is no
future/past constraint here (a Pydantic `date` already rejects a malformed value).
Domain validity — e.g. a date earlier than the status-holding period allows — is an
M3B rules concern, deliberately not enforced at this input boundary.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.residence.csv_import import CONTENT_MAX_LENGTH, ParsedImport, RowDiagnostic
from app.residence.domain import (
    DESTINATION_LABEL_MAX_LENGTH,
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

    destination_label: str = Field(min_length=1, max_length=DESTINATION_LABEL_MAX_LENGTH)
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


class CsvImportInput(BaseModel):
    # The CSV file's text content. The frontend reads the chosen file and posts its text;
    # this keeps the contract JSON and the schema simple for the generated client. Capped
    # (fail-closed → 422) so intake is bounded before real file uploads land in M4 (§11).
    content: str = Field(max_length=CONTENT_MAX_LENGTH)


class ImportRowErrorResponse(BaseModel):
    field: str
    code: str
    message: str


class ImportRowValueResponse(BaseModel):
    """The normalised values of a valid row, echoed back so the validate preview shows
    exactly what would be imported (dates canonicalised, country code upper-cased)."""

    destination_label: str
    destination_country_code: str | None
    departure_date: date
    return_date: date
    date_confidence: str
    review_state: str
    notes: str | None


class ImportRowResponse(BaseModel):
    row_number: int
    valid: bool
    errors: list[ImportRowErrorResponse]
    value: ImportRowValueResponse | None

    @classmethod
    def from_diagnostic(cls, diagnostic: RowDiagnostic) -> "ImportRowResponse":
        value = None
        if diagnostic.fields is not None:
            f = diagnostic.fields
            value = ImportRowValueResponse(
                destination_label=f.destination_label,
                destination_country_code=f.destination_country_code,
                departure_date=f.departure_date,
                return_date=f.return_date,
                date_confidence=f.date_confidence.value,
                review_state=f.review_state.value,
                notes=f.notes,
            )
        return cls(
            row_number=diagnostic.row_number,
            valid=diagnostic.valid,
            errors=[
                ImportRowErrorResponse(field=e.field, code=e.code, message=e.message)
                for e in diagnostic.errors
            ],
            value=value,
        )


class ImportValidationResponse(BaseModel):
    total: int
    valid_count: int
    error_count: int
    all_valid: bool
    rows: list[ImportRowResponse]

    @classmethod
    def from_parsed(cls, parsed: ParsedImport) -> "ImportValidationResponse":
        return cls(
            total=len(parsed.rows),
            valid_count=parsed.valid_count,
            error_count=parsed.error_count,
            all_valid=parsed.all_valid,
            rows=[ImportRowResponse.from_diagnostic(r) for r in parsed.rows],
        )


class ImportCommitResponse(BaseModel):
    imported_count: int
    records: list[TravelRecordResponse]
