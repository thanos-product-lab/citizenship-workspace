"""Case HTTP routes. Handlers stay thin: parse, delegate to the service, project."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.assessments import service as assessment_service
from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases import service
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.cases.schemas import CaseResponse, CreateCaseRequest
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CaseResponse)
def create_case(
    body: CreateCaseRequest,
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CaseResponse:
    case = service.create_case(session, user=user, title=body.title)
    phase = assessment_service.derive_case_phase(session, case=case)
    return CaseResponse.from_domain(case, phase=phase)


@router.get("", response_model=list[CaseResponse])
def list_cases(
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[CaseResponse]:
    cases = service.list_cases(session, user=user)
    # One batched derivation for the whole list, not one query per case.
    phases = assessment_service.derive_phases(session, cases=cases)
    return [CaseResponse.from_domain(c, phase=phases[c.id]) for c in cases]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> CaseResponse:
    phase = assessment_service.derive_case_phase(session, case=case)
    return CaseResponse.from_domain(case, phase=phase)


@router.delete("/{case_id}", response_model=CaseResponse)
def delete_case(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CaseResponse:
    """Request deletion: the case enters DELETION_PENDING and the purge is queued."""
    deleted = service.request_deletion(session, case=case, user=user)
    phase = assessment_service.derive_case_phase(session, case=deleted)
    return CaseResponse.from_domain(deleted, phase=phase)
