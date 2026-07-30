"""Proposed-application-date endpoints. Case access is checked before any handler.

    GET  /api/v1/cases/{case_id}/application-dates          → current date, or null
    POST /api/v1/cases/{case_id}/application-dates/select   → select or change it

Both mount under `require_case_access`, so the ownership boundary is enforced the same
way as every case-scoped read/command. The ACTIVE-case gate lives in the service.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.residence import service
from app.residence.domain import TravelRecordFields
from app.residence.schemas import (
    CsvImportInput,
    ImportCommitResponse,
    ImportValidationResponse,
    ProposedApplicationDateResponse,
    SelectApplicationDateInput,
    TravelRecordEditInput,
    TravelRecordInput,
    TravelRecordResponse,
)
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases/{case_id}/application-dates", tags=["application-dates"])

travel_records_router = APIRouter(
    prefix="/api/v1/cases/{case_id}/travel-records", tags=["travel-records"]
)


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
