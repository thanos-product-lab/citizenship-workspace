"""Requirements and assessment endpoints. Case access is checked before any handler.

    GET  /api/v1/cases/{case_id}/requirements                       → every requirement
    GET  /api/v1/cases/{case_id}/requirements/{requirement_key}     → one requirement's detail
    POST /api/v1/cases/{case_id}/assessments/recalculate            → run a trusted assessment

All mount under `require_case_access`, so the ownership boundary is enforced the same way
as every case-scoped read/command. The active-case and application-date gates live in the
service and surface as typed 409s.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.assessments import service
from app.assessments.schemas import RecalculateResponse, RequirementDetail, RequirementSummary
from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.shared.tenant import get_tenant_session

requirements_router = APIRouter(
    prefix="/api/v1/cases/{case_id}/requirements", tags=["requirements"]
)
assessments_router = APIRouter(prefix="/api/v1/cases/{case_id}/assessments", tags=["assessments"])


@requirements_router.get("", response_model=list[RequirementSummary])
def list_requirements(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> list[RequirementSummary]:
    projection = service.list_requirements(session, case=case)
    return [RequirementSummary.from_projection(d, r) for d, r in projection]


@requirements_router.get("/{requirement_key}", response_model=RequirementDetail)
def get_requirement(
    requirement_key: str,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> RequirementDetail:
    view = service.get_requirement_detail(session, case=case, requirement_key=requirement_key)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")
    return RequirementDetail.from_view(
        view.definition, view.current, view.input_links, view.guidance, view.history
    )


@assessments_router.post("/recalculate", response_model=RecalculateResponse)
def recalculate(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RecalculateResponse:
    outcome = service.recalculate(session, case=case, user=user)
    return RecalculateResponse.from_outcome(outcome.run, outcome.requirements, outcome.result_count)
