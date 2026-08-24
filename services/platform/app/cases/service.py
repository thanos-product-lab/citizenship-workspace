"""Case commands and queries. Domain logic lives here, never in the route handler.

`create_case` is the reference example of the M2 transactional contract: it builds
the aggregate and its owner membership, then commits state + event + audit + outbox
through a single `UnitOfWork`. There is no code path that persists a case without
its `CaseCreated` event.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.auth.schemas import CurrentUser
from app.cases.domain import (
    ApplicationCase,
    CaseCreated,
    CaseDeletionRequested,
    CaseMembership,
    LifecycleStatus,
)
from app.cases.repository import CaseRepository, MembershipRepository
from app.shared.unit_of_work import UnitOfWork


def create_case(session: Session, *, user: CurrentUser, title: str) -> ApplicationCase:
    case = ApplicationCase.create(owner_user_id=user.user_id, title=title)
    CaseRepository.add(session, case)
    MembershipRepository.add(session, CaseMembership.owner(case_id=case.id, user_id=user.user_id))

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        CaseCreated(aggregate_id=case.id, route_key=case.route_key),
        case_id=case.id,
        action="case.created",
        target_type="ApplicationCase",
        target_id=case.id,
    )
    uow.commit()
    session.refresh(case)  # load server-defaulted created_at / updated_at
    return case


def list_cases(session: Session, *, user: CurrentUser) -> list[ApplicationCase]:
    return CaseRepository.list_for_owner(session, user.user_id)


def get_case(session: Session, *, case_id: uuid.UUID, user: CurrentUser) -> ApplicationCase | None:
    """Return the case only if this user is an active member of it.

    Returns None both when the case does not exist and when the user is not a
    member — the two are deliberately indistinguishable to the caller so case
    existence never leaks across the ownership boundary (Domain §3.1)."""
    case = CaseRepository.get(session, case_id)
    if case is None:
        return None
    if not MembershipRepository.is_active_member(session, case_id, user.user_id):
        return None
    if case.lifecycle_status is LifecycleStatus.DELETED:
        # A deleted case is gone — never serve it, even before the purge worker
        # removes the row (defence for the terminal state; ADR-0005).
        return None
    return case


def lock_writable_case(session: Session, case_id: uuid.UUID) -> ApplicationCase | None:
    """Lock the case row for a write command. Callers hold the lock for the rest of
    the transaction, so a concurrent deletion serialises behind them (ADR-0005 R2)."""
    return CaseRepository.get_for_update(session, case_id)


def request_deletion(
    session: Session, *, case: ApplicationCase, user: CurrentUser
) -> ApplicationCase:
    """Move the case to DELETION_PENDING and queue the purge. Idempotency: a case
    already pending/deleted raises IllegalTransition (→ 409) from the aggregate."""
    locked = CaseRepository.get_for_update(session, case.id)
    if locked is None:  # vanished between the access check and the lock
        raise LookupError("case not found")
    locked.request_deletion(at=datetime.now(UTC))

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        CaseDeletionRequested(aggregate_id=locked.id),
        case_id=locked.id,
        action="case.deletion_requested",
        target_type="ApplicationCase",
        target_id=locked.id,
    )
    uow.commit()
    session.refresh(locked)
    return locked
