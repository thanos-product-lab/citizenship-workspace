"""Proposed-application-date endpoints. Case access is checked before any handler.

    GET  /api/v1/cases/{case_id}/application-dates          → current date, or null
    POST /api/v1/cases/{case_id}/application-dates/select   → select or change it
    POST /api/v1/cases/{case_id}/application-dates/simulate → preview another date

All mount under `require_case_access`, so the ownership boundary is enforced the same
way as every case-scoped read/command. The ACTIVE-case gate lives in the service.

`/simulate` writes nothing (Domain §10.3, §48.3). Its handler lives here because the URL
space for a proposed application date belongs here, while the logic lives in
`app.assessments.simulation` because evaluating requirements is that module's work — a
route composing two modules' services, not a module reaching into another's internals.
It is the second write-nothing POST in this file; `/travel-records/import/validate` is the
first, and both are POSTs only because they carry a body.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.assessments import simulation
from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.residence import service, timeline
from app.residence.domain import TravelRecordFields
from app.residence.schemas import (
    ApplicationDateSimulationResponse,
    CsvImportInput,
    ImportCommitResponse,
    ImportValidationResponse,
    ProposedApplicationDateResponse,
    SelectApplicationDateInput,
    SimulateApplicationDateInput,
    TimelineResponse,
    TravelRecordEditInput,
    TravelRecordInput,
    TravelRecordResponse,
)
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases/{case_id}/application-dates", tags=["application-dates"])

travel_records_router = APIRouter(
    prefix="/api/v1/cases/{case_id}/travel-records", tags=["travel-records"]
)

timeline_router = APIRouter(prefix="/api/v1/cases/{case_id}/timeline", tags=["timeline"])


@timeline_router.get("", response_model=TimelineResponse | None)
def get_timeline(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> TimelineResponse | None:
    """The residence timeline: window boundaries, per-trip counted days, and totals.

    `null` when no application date has been selected. Not a 409, unlike `/simulate`:
    there is no window and so no counted figure, but the trips themselves are real and the
    view can still list them — refusing the whole request would take that decision away
    from the client.
    """
    view = timeline.get_timeline(session, case=case)
    return TimelineResponse.from_domain(view) if view is not None else None


def _fields(body: TravelRecordInput) -> TravelRecordFields:
    return TravelRecordFields(
        destination_label=body.destination_label,
        departure_date=body.departure_date,
        return_date=body.return_date,
        date_confidence=body.date_confidence,
        review_state=body.review_state,
        destination_country_code=body.destination_country_code,
        notes=body.notes,
    )


@router.get("", response_model=ProposedApplicationDateResponse | None)
def get_application_date(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> ProposedApplicationDateResponse | None:
    outcome = service.get_current(session, case=case)
    if outcome is None:
        return None
    return ProposedApplicationDateResponse.from_domain(outcome.root, outcome.version)


@router.post("/simulate", response_model=ApplicationDateSimulationResponse)
def simulate_application_date(
    body: SimulateApplicationDateInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> ApplicationDateSimulationResponse:
    """Preview a candidate application date. Changes nothing.

    No `CurrentUser` dependency, deliberately: nothing here is attributed to an actor
    because nothing here is recorded. The caller is already authenticated and their
    ownership already checked by `require_case_access`; a simulation additionally has no
    `created_by` to fill in, and taking the user would invite one.

    409 when the case has no selected application date — there is no "before" side to
    compare against, and half a comparison is worse than a clear refusal.
    """
    view = simulation.simulate_application_date(
        session, case=case, candidate_date=body.candidate_application_date
    )
    return ApplicationDateSimulationResponse.from_domain(view)


@router.post("/select", response_model=ProposedApplicationDateResponse)
def select_application_date(
    body: SelectApplicationDateInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProposedApplicationDateResponse:
    outcome = service.select_application_date(
        session,
        case=case,
        user=user,
        application_date=body.application_date,
        expected_revision=body.expected_revision,
    )
    return ProposedApplicationDateResponse.from_domain(outcome.root, outcome.version)


@travel_records_router.get("", response_model=list[TravelRecordResponse])
def list_travel_records(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> list[TravelRecordResponse]:
    outcomes = service.list_travel_records(session, case=case)
    return [TravelRecordResponse.from_domain(o.record, o.version) for o in outcomes]


@travel_records_router.post(
    "", response_model=TravelRecordResponse, status_code=status.HTTP_201_CREATED
)
def add_travel_record(
    body: TravelRecordInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TravelRecordResponse:
    outcome = service.add_travel_record(session, case=case, user=user, fields=_fields(body))
    return TravelRecordResponse.from_domain(outcome.record, outcome.version)


@travel_records_router.patch("/{travel_record_id}", response_model=TravelRecordResponse)
def edit_travel_record(
    travel_record_id: uuid.UUID,
    body: TravelRecordEditInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> TravelRecordResponse:
    outcome = service.edit_travel_record(
        session,
        case=case,
        user=user,
        travel_record_id=travel_record_id,
        fields=_fields(body),
        expected_revision=body.expected_revision,
    )
    return TravelRecordResponse.from_domain(outcome.record, outcome.version)


@travel_records_router.delete("/{travel_record_id}", response_model=TravelRecordResponse)
def remove_travel_record(
    travel_record_id: uuid.UUID,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    expected_revision: Annotated[int | None, Query()] = None,
) -> TravelRecordResponse:
    outcome = service.remove_travel_record(
        session,
        case=case,
        user=user,
        travel_record_id=travel_record_id,
        expected_revision=expected_revision,
    )
    return TravelRecordResponse.from_domain(outcome.record, outcome.version)


@travel_records_router.post("/import/validate", response_model=ImportValidationResponse)
def validate_travel_import(
    body: CsvImportInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> ImportValidationResponse:
    parsed = service.validate_csv_import(session, case=case, content=body.content)
    return ImportValidationResponse.from_parsed(parsed)


@travel_records_router.post(
    "/import", response_model=ImportCommitResponse, status_code=status.HTTP_201_CREATED
)
def commit_travel_import(
    body: CsvImportInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ImportCommitResponse:
    outcomes = service.import_travel_records(session, case=case, user=user, content=body.content)
    return ImportCommitResponse(
        imported_count=len(outcomes),
        records=[TravelRecordResponse.from_domain(o.record, o.version) for o in outcomes],
    )
