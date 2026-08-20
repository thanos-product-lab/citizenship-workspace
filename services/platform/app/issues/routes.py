"""Issue queue endpoints. Case access is checked before any handler.

    GET  /api/v1/cases/{case_id}/issues                      → the issue queue
    POST /api/v1/cases/{case_id}/issues/{issue_id}/dismiss   → set a dismissible issue aside

Both mount under `require_case_access`, the same ownership boundary as every case-scoped
read or command.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.issues import service
from app.issues.domain import IssueResolution
from app.issues.repository import IssueRepository
from app.issues.schemas import IssueQueue, IssueView
from app.shared.tenant import get_tenant_session
from app.shared.unit_of_work import UnitOfWork

router = APIRouter(prefix="/api/v1/cases/{case_id}/issues", tags=["issues"])


@router.get("", response_model=IssueQueue)
def get_issue_queue(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> IssueQueue:
    issues = IssueRepository.list_for_case(session, case.id)
    resolutions = IssueRepository.list_resolutions(session, [issue.id for issue in issues])
    by_issue: dict[uuid.UUID, list[IssueResolution]] = {}
    for resolution in resolutions:
        by_issue.setdefault(resolution.issue_id, []).append(resolution)
    return IssueQueue.build(case_id=case.id, issues=issues, resolutions_by_issue=by_issue)


@router.post("/{issue_id}/dismiss", response_model=IssueView)
def dismiss_issue(
    issue_id: uuid.UUID,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> IssueView:
    uow = UnitOfWork(session, actor_id=user.user_id)
    try:
        issue = service.dismiss(
            session, uow, case_id=case.id, issue_id=issue_id, actor_id=user.user_id
        )
    except service.IssueNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="issue not found"
        ) from None
    uow.commit()
    session.refresh(issue)
    return IssueView.of(issue, IssueRepository.list_resolutions(session, [issue.id]))
