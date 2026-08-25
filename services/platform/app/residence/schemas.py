"""Boundary schemas for selecting a proposed application date.

A proposed application date is a forward-looking planning intention, so there is no
future/past constraint here (a Pydantic `date` already rejects a malformed value).
Domain validity — e.g. a date earlier than the status-holding period allows — is an
M3B rules concern, deliberately not enforced at this input boundary.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.assessments.schemas import (
    LimitationView,
    NextActionView,
    RenderedMessage,
    StaleInformation,
)
from app.assessments.simulation import (
    SimulatedRequirement,
    SimulatedWindows,
    SimulationView,
)
from app.requirements.messages import render_summary
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
from app.residence.timeline import TimelineProjection

#: A sane calendar range for an application date, shared by the save and the preview.
#: Not a domain rule — the rules spec has nothing to say about how far ahead someone may
#: plan — but `qualifying_window` subtracts five years, so a date before year six raises
#: `ValueError: year -4 is out of range` from the stdlib and surfaces as a 500. A simulator
#: is a free-text date field whose whole purpose is trying values, which makes that
#: reachable by typing. Bounded here so the answer is a 422 naming the field, and bounded
#: identically on both endpoints so a date the preview accepts is a date the save accepts.
MIN_APPLICATION_DATE = date(1900, 1, 1)
MAX_APPLICATION_DATE = date(2100, 12, 31)


class SelectApplicationDateInput(BaseModel):
    application_date: date = Field(ge=MIN_APPLICATION_DATE, le=MAX_APPLICATION_DATE)
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
    #: Documents the user has attached to this trip (Domain §11.9).
    #:
    #: Ids only, and deliberately so. §11.8 requires a trip to "expose its support state",
    #: which is a question about coverage, not about the documents — sending their names
    #: and page counts here would duplicate the evidence library into every trip row and
    #: make two places to keep in step. The client already holds the library and joins by
    #: id.
    #:
    #: Empty means unevidenced. It does **not** mean the trip is unsupported in any
    #: judged sense: nothing has read these documents to decide whether they support the
    #: trip, and nothing does until M8.
    supporting_evidence_item_ids: list[uuid.UUID] = []
    revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        record: TravelRecord,
        version: TravelRecordVersion,
        supporting_evidence_item_ids: Sequence[uuid.UUID] = (),
    ) -> "TravelRecordResponse":
        return cls(
            supporting_evidence_item_ids=list(supporting_evidence_item_ids),
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


class AttachEvidenceInput(BaseModel):
    """Which document to attach. The trip is in the path.

    A body rather than a second path segment because the *document* is what the user
    picked in this interaction — the trip is the row they were already looking at.
    """

    evidence_item_id: uuid.UUID


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


# --- Application-date simulation (Domain §42.2, §48.3) -----------------------


class SimulateApplicationDateInput(BaseModel):
    """The one thing a simulation takes. No `expected_revision`: nothing is being written,
    so there is no version to be stale against — the concurrency check belongs on the save
    that follows, where `/select` already has one."""

    candidate_application_date: date = Field(ge=MIN_APPLICATION_DATE, le=MAX_APPLICATION_DATE)


class SimulatedWindowsResponse(BaseModel):
    qualifying_period_start: date
    qualifying_period_end: date
    final_year_start: date
    final_year_end: date
    presence_anchor: date

    @classmethod
    def from_domain(cls, windows: SimulatedWindows) -> "SimulatedWindowsResponse":
        return cls(
            qualifying_period_start=windows.qualifying_period.start,
            qualifying_period_end=windows.qualifying_period.end,
            final_year_start=windows.final_year.start,
            final_year_end=windows.final_year.end,
            presence_anchor=windows.presence_anchor,
        )


class SimulatedBefore(BaseModel):
    """What the case says today, currency included.

    A stale conclusion is reported as stale rather than quietly recomputed. The comparison
    is against what the case actually concluded, not against what it would conclude if it
    were rerun — those are different questions, and conflating them would let a simulation
    silently launder a stale result into a fresh-looking baseline."""

    conclusion: str
    currency: str | None
    summary_code: str | None
    summary: RenderedMessage | None
    summary_parameters: dict[str, object]
    limitations: list[LimitationView]
    #: Why the current conclusion is no longer current, when it is not. The client renders
    #: the same `StaleAssessmentNotice` it renders everywhere else rather than being handed
    #: a bare "STALE" string it cannot explain.
    stale: StaleInformation | None


class SimulatedAfter(BaseModel):
    """What the rules conclude at the candidate date — and nothing that could be mistaken
    for a stored result.

    `currency` is a `Literal["PROVISIONAL"]`, so there is no code path by which this object
    can report itself as current (Domain §42.2). There is no run id, no result id, and no
    input links, because none of those exist: the simulation persists nothing, and the
    conclusion was drawn at a date no versioned input carries."""

    currency: Literal["PROVISIONAL"] = "PROVISIONAL"
    conclusion: str
    summary_code: str | None
    summary: RenderedMessage | None
    #: Careful: `provisional_days` in here means "counting unconfirmed travel records"
    #: (RULES_SPEC §6.2) and has nothing to do with `currency: "PROVISIONAL"`, which means
    #: "not saved". Two unrelated senses of one word, in one object. User-facing copy should
    #: say "preview" for the first and "unconfirmed records" for the second, and never
    #: "provisional" for either.
    summary_parameters: dict[str, object]
    calculation_breakdown: dict[str, object]
    limitations: list[LimitationView]
    #: Carried for symmetry with `limitations`, and because dropping them was asymmetric:
    #: the presence rule's resolving date is lifted to the top of the response while
    #: `status.holding_period`'s blocking `SELECT_APPLICATION_DATE` action would have been
    #: silently discarded. A candidate date that satisfies presence but breaks the holding
    #: period must be able to say so.
    next_actions: list[NextActionView]


class SimulatedChange(BaseModel):
    """What actually moved, dimension by dimension.

    A single `conclusion_changed` flag is not enough, and `residence.travel_consistency` is
    why: it is a data-quality rule whose entire output is limitations (RULES_SPEC §7.8), so
    moving past the trip that covered the presence anchor swaps
    `NEAR_STANDARD_THRESHOLD` for `TRAVEL_OUTSIDE_WINDOW` while the conclusion and the
    summary code both stay put. A conclusion-only flag reports that as "nothing changed"
    — for the requirement whose job is surfacing exactly this.

    `summary_parameters` catches the other silent case: 439 → 429 days is a real change the
    user must see, and both figures sit in the same NEAR_THRESHOLD band."""

    conclusion: bool
    summary_code: bool
    summary_parameters: bool
    limitations: bool
    any: bool


class SimulatedRequirementResponse(BaseModel):
    requirement_key: str
    title: str
    group_key: str
    display_order: int
    changed: SimulatedChange
    before: SimulatedBefore
    after: SimulatedAfter

    @classmethod
    def from_domain(cls, row: SimulatedRequirement) -> "SimulatedRequirementResponse":
        before_limitations = [LimitationView.of(raw) for raw in row.before_limitations]
        after_limitations = [
            LimitationView.of(limitation.as_dict()) for limitation in row.after.limitations
        ]
        changed = SimulatedChange(
            conclusion=row.before_conclusion != row.after.conclusion,
            summary_code=row.before_summary_code != row.after.summary_code,
            summary_parameters=row.before_summary_parameters != row.after.summary_parameters,
            limitations=sorted(item.code for item in before_limitations)
            != sorted(item.code for item in after_limitations),
            any=False,  # replaced below; a field cannot read its siblings during construction
        )
        return cls(
            requirement_key=row.definition.requirement_key,
            title=row.definition.title,
            group_key=row.definition.group_key,
            display_order=row.definition.display_order,
            changed=changed.model_copy(
                update={
                    "any": any(
                        (
                            changed.conclusion,
                            changed.summary_code,
                            changed.summary_parameters,
                            changed.limitations,
                        )
                    )
                }
            ),
            before=SimulatedBefore(
                conclusion=row.before_conclusion,
                currency=row.before_currency,
                summary_code=row.before_summary_code,
                summary=RenderedMessage.build(
                    row.before_summary_code, row.before_summary_parameters, render_summary
                ),
                summary_parameters=row.before_summary_parameters,
                limitations=before_limitations,
                stale=StaleInformation.of(
                    row.before_currency, row.before_stale_reason_code, row.before_marked_stale_at
                ),
            ),
            after=SimulatedAfter(
                conclusion=row.after.conclusion,
                summary_code=row.after.summary_code,
                summary=RenderedMessage.build(
                    row.after.summary_code, row.after.summary_parameters, render_summary
                ),
                summary_parameters=row.after.summary_parameters,
                calculation_breakdown=row.after.calculation_breakdown,
                limitations=after_limitations,
                next_actions=[
                    NextActionView.of(action.as_dict()) for action in row.after.next_actions
                ],
            ),
        )


class ApplicationDateSimulationResponse(BaseModel):
    """A preview, and shaped so it cannot be read as anything else.

    `saved: false` and `mode: "PROVISIONAL"` are literals, `candidate_application_date` sits
    beside `current_application_date` so the two are never confused, and the per-requirement
    type is deliberately *not* `RequirementSummary` — after `just api-client` the generated
    TypeScript types differ, so a simulated value cannot be passed where a real result is
    expected without a compile error."""

    saved: Literal[False] = False
    mode: Literal["PROVISIONAL"] = "PROVISIONAL"
    current_application_date: date
    candidate_application_date: date = Field(ge=MIN_APPLICATION_DATE, le=MAX_APPLICATION_DATE)
    #: `None` until the case has been assessed once — the before side is read from the
    #: persisted result, and before there is a result there are no before windows.
    windows_before: SimulatedWindowsResponse | None
    windows_after: SimulatedWindowsResponse
    #: The nearest later date the presence rule found clear of confirmed absence, if it
    #: looked. Lifted out of the rule's parameters because it is the value that turns
    #: "not currently satisfied" into an action (RULES_SPEC §7.5).
    resolving_application_date: date | None
    requirements: list[SimulatedRequirementResponse]

    @classmethod
    def from_domain(cls, view: SimulationView) -> "ApplicationDateSimulationResponse":
        return cls(
            current_application_date=view.current_application_date,
            candidate_application_date=view.candidate_application_date,
            windows_before=(
                SimulatedWindowsResponse.from_domain(view.windows_before)
                if view.windows_before is not None
                else None
            ),
            windows_after=SimulatedWindowsResponse.from_domain(view.windows_after),
            resolving_application_date=view.resolving_application_date,
            requirements=[
                SimulatedRequirementResponse.from_domain(row) for row in view.requirements
            ],
        )


# --- Residence timeline (Domain §44.3) ---------------------------------------


class TimelineTripResponse(BaseModel):
    """One trip, with the two day counts kept apart.

    `absent_days` is how long the trip was; `counted_days` is how much of it falls inside
    the qualifying window. They differ for any trip straddling a boundary — the canonical
    case's first trip is abroad 11 days and contributes 10 — and publishing only the second
    would leave the user unable to see why their arithmetic disagrees with ours."""

    travel_record_id: uuid.UUID
    destination_label: str
    departure_date: date
    return_date: date
    date_confidence: str
    review_state: str
    is_trusted: bool
    absent_days: int
    counted_days: int
    is_outside_window: bool
    covers_presence_anchor: bool
    overlaps_with: list[uuid.UUID]


class TimelineTotalsResponse(BaseModel):
    qualifying_period_days: int
    final_year_days: int
    #: Counting unconfirmed records too (RULES_SPEC §6.2) — a different sense of
    #: "provisional" from the simulation's, and named to avoid borrowing that word.
    qualifying_period_days_including_unconfirmed: int
    final_year_days_including_unconfirmed: int
    trip_count: int
    unconfirmed_trip_count: int


class TimelineResponse(BaseModel):
    """The residence picture as the records currently stand.

    No conclusion and no currency anywhere in it: those belong to `AssessmentResult`
    (ADR-0007), and a second surface publishing its own would be a second answer to the
    same question. `assessment_is_stale` is the one link between the two — it says the
    conclusions on the Requirements destination were reached before these records, so a
    figure here that disagrees with one there is explained rather than mysterious."""

    application_date: date
    qualifying_period_start: date
    qualifying_period_end: date
    final_year_start: date
    final_year_end: date
    presence_anchor: date
    presence_anchor_is_absent: bool
    assessment_is_stale: bool
    totals: TimelineTotalsResponse
    trips: list[TimelineTripResponse]

    @classmethod
    def from_domain(cls, view: TimelineProjection) -> "TimelineResponse":
        return cls(
            application_date=view.application_date,
            qualifying_period_start=view.qualifying_period.start,
            qualifying_period_end=view.qualifying_period.end,
            final_year_start=view.final_year.start,
            final_year_end=view.final_year.end,
            presence_anchor=view.presence_anchor,
            presence_anchor_is_absent=view.presence_anchor_is_absent,
            assessment_is_stale=view.assessment_is_stale,
            totals=TimelineTotalsResponse(**vars(view.totals)),
            trips=[
                TimelineTripResponse(**{**vars(trip), "overlaps_with": list(trip.overlaps_with)})
                for trip in view.trips
            ],
        )
