"""Proposed-application-date endpoints. Case access is checked before any handler.

    GET  /api/v1/cases/{case_id}/application-dates          → current date, or null
    POST /api/v1/cases/{case_id}/application-dates/select   → select or change it

Both mount under `require_case_access`, so the ownership boundary is enforced the same
way as every case-scoped read/command. The ACTIVE-case gate lives in the service.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.residence import service
from app.residence.schemas import ProposedApplicationDateResponse, SelectApplicationDateInput
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases/{case_id}/application-dates", tags=["application-dates"])


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
