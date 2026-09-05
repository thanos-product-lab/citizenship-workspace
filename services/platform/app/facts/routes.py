"""The review queue, the review command, and the case's trusted facts.

Under `/api/v1/cases/{case_id}/…` like every case-scoped aggregate — the prefix is what
keeps one from being addressable outside its case, asserted by
`test_no_case_scoped_aggregate_is_addressable_outside_a_case_prefix`.

**There is no bulk endpoint, and that is the implementation of MVP §8.11's ban on bulk
confirmation for high-risk date fields.** Not a filter that rejects date claims from a
batch — no batch route exists, so there is nothing to call with one. Every remaining
field is low enough value that a batch would earn nothing, and a route that does not
exist cannot acquire a special case later without someone writing it deliberately.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.facts import service
from app.facts.schemas import (
    ClaimQueueResponse,
    ClaimView,
    FactsResponse,
    FactView,
    ReviewRequest,
    ReviewResponse,
)
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases/{case_id}", tags=["claims"])


@router.get("/claims", response_model=ClaimQueueResponse)
def list_claims(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> ClaimQueueResponse:
    """Claims awaiting a decision.

    `PENDING_REVIEW` only. A rejected or already-confirmed claim in a queue invites a
    second decision, which would either duplicate a fact or resurrect a refusal.
    """
    claims = service.list_pending(session, case=case)
    return ClaimQueueResponse(items=[ClaimView.of(claim) for claim in claims])


@router.post(
    "/claims/{claim_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def review_claim(
    claim_id: uuid.UUID,
    body: ReviewRequest,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReviewResponse:
    """Decide about one claim, and create the fact it authorises.

    201, because the thing that happened is that a decision — and usually a fact version
    — came into existence. A 200 would describe this as reading something.
    """
    outcome = service.review(
        session,
        case=case,
        claim_id=claim_id,
        user_id=user.user_id,
        entered_value=body.entered_value,
        decision=body.decision,
        reason_code=body.reason_code,
    )
    version = outcome.fact_version
    return ReviewResponse(
        claim_id=outcome.claim.id,
        claim_status=outcome.claim.status,
        decision=outcome.decision.decision,
        review_mode=outcome.decision.review_mode,
        fact_version_id=version.id if version else None,
        fact_version_number=version.version_number if version else None,
        value=version.raw_value if version else None,
    )


@router.get("/facts", response_model=FactsResponse)
def list_facts(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> FactsResponse:
    """The case's trusted values, current version only.

    Returns `FactView`, built from a `FactVersion`. There is no shape here that a claim
    could be serialised into, so an untrusted proposal cannot reach this response by
    any route.
    """
    rows = service.current_facts(session, case=case)
    return FactsResponse(items=[FactView.of(fact, version) for fact, version in rows])
