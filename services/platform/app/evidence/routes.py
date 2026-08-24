"""Evidence HTTP surface.

Every route sits under `/api/v1/cases/{case_id}/…` and depends on `require_case_access`.
Both are load-bearing and both are now tested rather than conventional:

- the dependency is what enters the RLS tenant context, asserted for *every* route by
  `test_every_route_enters_a_tenant_or_is_allowlisted`;
- the prefix is what keeps a case-scoped aggregate from being addressable outside its
  case, asserted by `test_no_case_scoped_aggregate_is_addressable_outside_a_case_prefix`.

The second exists because of this module. A `GET /api/v1/evidence/{evidence_id}/download`
is case-scoped and would have been invisible to the M5 route check, which selected routes
by the literal `{case_id}` in the path — the M5 notes named that shape as the one that
would slip through at M7.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.cases.dependencies import require_case_access
from app.cases.domain import ApplicationCase
from app.core.config import get_settings
from app.core.storage import StorageAdapter, get_storage
from app.evidence import service
from app.evidence.repository import EvidenceRepository
from app.evidence.schemas import (
    EvidenceContentResponse,
    EvidenceLibraryResponse,
    EvidenceResponse,
    RecordUploadRequest,
    StartUploadRequest,
    UploadGrantResponse,
)
from app.shared.tenant import get_tenant_session

router = APIRouter(prefix="/api/v1/cases/{case_id}/evidence", tags=["evidence"])


@router.post("/uploads", response_model=UploadGrantResponse)
def start_upload(
    body: StartUploadRequest,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    # The tenant session is unused by this handler - it writes nothing - but the
    # dependency stays: it is what enters the RLS context, and a case-scoped route that
    # opts out of it is the exact shape `test_every_route_enters_a_tenant_or_is_allowlisted`
    # exists to catch. An allowlist entry here would be a lie.
    session: Annotated[Session, Depends(get_tenant_session)],
    storage: Annotated[StorageAdapter, Depends(get_storage)],
) -> UploadGrantResponse:
    grant = service.start_upload(
        storage,
        case=case,
        media_type=body.media_type,
        declared_size_bytes=body.declared_size_bytes,
    )
    return UploadGrantResponse.from_domain(grant)


@router.post("", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def record_upload(
    body: RecordUploadRequest,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    storage: Annotated[StorageAdapter, Depends(get_storage)],
) -> EvidenceResponse:
    item, file = service.record_upload(
        session,
        storage,
        case=case,
        user=user,
        token=body.upload_token,
        category=body.category,
        display_name=body.display_name,
        original_filename=body.original_filename,
    )
    return EvidenceResponse.from_domain(item, file)


@router.get("", response_model=EvidenceLibraryResponse)
def list_evidence(
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> EvidenceLibraryResponse:
    rows = service.list_evidence(session, case=case)
    runs = EvidenceRepository.latest_runs_for_case(session, case_id=case.id)
    return EvidenceLibraryResponse(
        items=[EvidenceResponse.from_domain(item, file, runs.get(item.id)) for item, file in rows],
        max_upload_bytes=get_settings().max_upload_bytes,
    )


@router.get("/{evidence_item_id}", response_model=EvidenceResponse)
def get_evidence(
    evidence_item_id: uuid.UUID,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
) -> EvidenceResponse:
    item, file = service.get_evidence(session, case=case, evidence_item_id=evidence_item_id)
    run = EvidenceRepository.latest_run(session, evidence_item_id=item.id)
    return EvidenceResponse.from_domain(item, file, run)


@router.get("/{evidence_item_id}/content", response_model=EvidenceContentResponse)
def get_content_url(
    evidence_item_id: uuid.UUID,
    case: Annotated[ApplicationCase, Depends(require_case_access)],
    session: Annotated[Session, Depends(get_tenant_session)],
    storage: Annotated[StorageAdapter, Depends(get_storage)],
) -> EvidenceContentResponse:
    url, ttl = service.content_url(session, storage, case=case, evidence_item_id=evidence_item_id)
    return EvidenceContentResponse(url=url, expires_in_seconds=ttl)
