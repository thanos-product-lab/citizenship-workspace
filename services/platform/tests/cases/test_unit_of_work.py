"""The transactional contract: state, event, audit, and outbox move together.

Locks constraint (3): a commit that changes business state without emitting a
domain event is impossible, and a successful command writes all four rows in one
transaction.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cases import service
from app.cases.domain import ApplicationCase
from app.shared.errors import StateWithoutEventError
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
