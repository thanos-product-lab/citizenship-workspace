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
from app.applicants.schemas import (
    ConfirmRequest,
    RequirementOutcomeResponse,
    RouteProfileDraftInput,
    RouteProfileResponse,
    RouteSupportResponse,
)
from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases/{case_id}/route-profile", tags=["route-profile"])


@router.get("", response_model=RouteProfileResponse | None)
def get_route_profile(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
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
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RouteProfileResponse:
    profile, version = service.save_draft(session, case=case, user=user, answers=body)
    return RouteProfileResponse.from_domain(profile, version)


@router.post("/confirm", response_model=RouteSupportResponse)
def confirm_route_profile(
    body: ConfirmRequest,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> RouteSupportResponse:
    outcome = service.confirm_route_profile(
        session, case=case, user=user, expected_revision=body.expected_revision
    )
    d = outcome.decision
    return RouteSupportResponse(
        support_status=outcome.support.value,
        lifecycle_status=outcome.case.lifecycle_status.value,
        conclusion=d.composite.conclusion.value,
        summary_code=d.composite.summary_code,
        confirmed_version_number=outcome.confirmed.version_number,
        rule_set=d.rule_set,
        semantic_version=d.semantic_version,
        requirements=[
            RequirementOutcomeResponse(
                requirement_key=o.requirement_key,
                conclusion=o.conclusion.value,
                summary_code=o.summary_code,
            )
            for o in d.outcomes
        ],
    )
