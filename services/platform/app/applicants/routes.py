"""Route-profile onboarding endpoints. Case access is checked before any handler.

    GET /api/v1/cases/{case_id}/route-profile   → current draft, or null if not started
    PUT /api/v1/cases/{case_id}/route-profile   → create or update the draft in place

Both mount under `require_case_access`, so the ownership boundary is enforced the
same way every case-scoped read/command is.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.applicants import service
from app.applicants.schemas import RouteProfileDraftInput, RouteProfileResponse
from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.shared.db import get_db

router = APIRouter(prefix="/api/v1/cases/{case_id}/route-profile", tags=["route-profile"])


@router.get("", response_model=RouteProfileResponse | None)
def get_route_profile(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_db)],
) -> RouteProfileResponse | None:
    result = service.get_draft(session, case=case)
    if result is None:
        return None
    profile, version = result
    return RouteProfileResponse.from_domain(profile, version)


@router.put("", response_model=RouteProfileResponse)
def save_route_profile(
    body: RouteProfileDraftInput,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RouteProfileResponse:
    profile, version = service.save_draft(session, case=case, user=user, answers=body)
    return RouteProfileResponse.from_domain(profile, version)
