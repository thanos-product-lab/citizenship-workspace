"""The case-access dependency: the single choke point for case-scoped reads.

Both the absent case and the unowned case return an identical 404 from one raise
site, so a caller cannot distinguish "does not exist" from "not yours". That
indistinguishability is the property tested in `tests/cases/test_ownership.py`.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases import service
from app.cases.domain import ApplicationCase
from app.shared.db import get_db

_CASE_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


def require_case_access(
    case_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApplicationCase:
    case = service.get_case(session, case_id=case_id, user=user)
    if case is None:
        raise _CASE_NOT_FOUND
    return case
