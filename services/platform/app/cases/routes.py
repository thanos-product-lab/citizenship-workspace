"""Case HTTP routes. Handlers stay thin: parse, delegate to the service, project."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

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
    return CaseResponse.from_domain(case)


@router.get("", response_model=list[CaseResponse])
def list_cases(
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[CaseResponse]:
    return [CaseResponse.from_domain(c) for c in service.list_cases(session, user=user)]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
) -> CaseResponse:
    return CaseResponse.from_domain(case)


@router.delete("/{case_id}", response_model=CaseResponse)
def delete_case(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CaseResponse:
    """Request deletion: the case enters DELETION_PENDING and the purge is queued."""
    deleted = service.request_deletion(session, case=case, user=user)
    return CaseResponse.from_domain(deleted)
