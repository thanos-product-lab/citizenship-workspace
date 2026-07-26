"""The transactional contract: state, event, audit, and outbox move together.

Locks constraint (3): a commit that changes business state without emitting a
domain event is impossible, and a successful command writes all four rows in one
transaction.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.applicants.domain import RouteProfile, RouteProfileDraftSaved
from app.cases import service
from app.cases.domain import ApplicationCase
from app.shared.errors import ConcurrencyConflict, StateWithoutEventError
from app.shared.records import AuditEntryRecord, DomainEventRecord, OutboxEventRecord
from app.shared.unit_of_work import UnitOfWork
from tests.conftest import as_user

pytestmark = pytest.mark.integration


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_state_without_event_is_rejected(db_session: Session) -> None:
    db_session.add(ApplicationCase.create(owner_user_id="user_a", title="X"))
    uow = UnitOfWork(db_session, actor_id="user_a")  # nothing emitted

    with pytest.raises(StateWithoutEventError):
        uow.commit()

    # The rejected commit persisted nothing.
    assert _count(db_session, ApplicationCase) == 0


def test_unique_violation_on_insert_becomes_a_conflict(db_session: Session) -> None:
    """A concurrent first-INSERT of a unique aggregate is a conflict, not a 500."""
    case = service.create_case(db_session, user=as_user("user_a"), title="X")

    # A profile already exists for this case (as a racing writer would have created).
    db_session.add(RouteProfile.start(case_id=case.id))
    db_session.flush()

    # A second profile for the same case violates the unique case_id index.
    dupe = RouteProfile.start(case_id=case.id)
    db_session.add(dupe)
    uow = UnitOfWork(db_session, actor_id="user_a")
    uow.emit(
        RouteProfileDraftSaved(aggregate_id=dupe.id, version_number=1, answered_fields=()),
        case_id=case.id,
        action="route_profile.draft_saved",
        target_type="RouteProfile",
        target_id=dupe.id,
    )
    with pytest.raises(ConcurrencyConflict):
        uow.commit()


def test_create_case_writes_state_event_audit_and_outbox(db_session: Session) -> None:
    case = service.create_case(db_session, user=as_user("user_a"), title="My case")

    assert _count(db_session, ApplicationCase) == 1
    assert _count(db_session, DomainEventRecord) == 1
    assert _count(db_session, AuditEntryRecord) == 1
    assert _count(db_session, OutboxEventRecord) == 1

    event = db_session.scalar(select(DomainEventRecord))
    assert event is not None
    assert event.event_type == "CaseCreated"
    assert event.aggregate_id == case.id
    # Narrow, non-identifying payload (§38.1): the free-text title never appears.
    assert event.payload == {"case_id": str(case.id), "route_key": case.route_key}
    assert "title" not in event.payload

    outbox = db_session.scalar(select(OutboxEventRecord))
    assert outbox is not None
    assert outbox.event_type == "CaseCreated"
    assert outbox.published_at is None  # pending delivery


def test_create_case_is_owned_by_its_creator(db_session: Session) -> None:
    case = service.create_case(db_session, user=as_user("user_a"), title="My case")
    assert case.owner_user_id == "user_a"
    assert isinstance(case.id, uuid.UUID)
