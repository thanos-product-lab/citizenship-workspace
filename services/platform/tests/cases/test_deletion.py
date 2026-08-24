"""Case deletion: the case enters DELETION_PENDING, writes stop, and the purge is
queued. Terminal purge (→ DELETED, records removed) is a later slice; the read
guard for DELETED is covered here directly.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.cases import service
from app.cases.domain import ApplicationCase, CaseMembership, LifecycleStatus
from app.shared.db import get_sessionmaker
from app.shared.records import DomainEventRecord, OutboxEventRecord
from app.shared.tenant import set_tenant
from tests.conftest import as_user

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _create_case(api: Api, user: str) -> str:
    return str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])


def test_delete_moves_case_to_deletion_pending(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    resp = api("user_a").delete(f"/api/v1/cases/{case_id}")
    assert resp.status_code == 200
    assert resp.json()["lifecycle_status"] == "DELETION_PENDING"
    # Still readable as a pending case (not yet purged).
    assert (
        api("user_a").get(f"/api/v1/cases/{case_id}").json()["lifecycle_status"]
        == "DELETION_PENDING"
    )


def test_delete_queues_a_deletion_event_and_outbox_row(api: Api, db_session: Session) -> None:
    case_id = _create_case(api, "user_a")
    api("user_a").delete(f"/api/v1/cases/{case_id}")

    event = db_session.scalar(
        select(DomainEventRecord).where(DomainEventRecord.event_type == "CaseDeletionRequested")
    )
    assert event is not None
    assert event.payload == {"case_id": case_id}
    outbox = db_session.scalar(
        select(func.count())
        .select_from(OutboxEventRecord)
        .where(OutboxEventRecord.event_type == "CaseDeletionRequested")
    )
    assert outbox == 1


def test_writes_are_blocked_once_deletion_is_pending(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    api("user_a").delete(f"/api/v1/cases/{case_id}")

    save = api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json={"status_type": "ILR"})
    assert save.status_code == 409
    confirm = api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert confirm.status_code == 409


def test_second_delete_conflicts(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    assert api("user_a").delete(f"/api/v1/cases/{case_id}").status_code == 200
    assert api("user_a").delete(f"/api/v1/cases/{case_id}").status_code == 409


def test_other_user_cannot_delete(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    assert api("user_b").delete(f"/api/v1/cases/{case_id}").status_code == 404
    # And the owner's case is untouched.
    assert api("user_a").get(f"/api/v1/cases/{case_id}").json()["lifecycle_status"] == "DRAFT"


def test_lock_reads_fresh_lifecycle_despite_a_stale_cached_instance(db_session: Session) -> None:
    """The R2 fix, precisely: `lock_writable_case` must return the *current* lifecycle
    even when this session already holds the case cached with a stale value. Without
    `populate_existing` the locked SELECT returns the cached DRAFT instance and the
    re-check is defeated — this test fails without the fix."""
    case = ApplicationCase.create(owner_user_id="user_a", title="X")
    db_session.add(case)
    db_session.add(CaseMembership.owner(case_id=case.id, user_id="user_a"))
    db_session.commit()
    assert case.lifecycle_status is LifecycleStatus.DRAFT  # cached as DRAFT

    # A concurrent deleter (separate session, same tenant) flips the row.
    other = get_sessionmaker()()
    try:
        set_tenant(other, "user_a")  # RLS: the deleter must own the row it updates
        other.execute(
            update(ApplicationCase)
            .where(ApplicationCase.id == case.id)
            .values(_lifecycle_status=LifecycleStatus.DELETION_PENDING.value)
        )
        other.commit()
    finally:
        other.close()

    assert case._lifecycle_status == LifecycleStatus.DRAFT.value  # still stale in-session

    locked = service.lock_writable_case(db_session, case.id)
    assert locked is not None
    assert locked.lifecycle_status is LifecycleStatus.DELETION_PENDING  # refreshed under lock


def test_list_never_includes_a_deleted_case(db_session: Session) -> None:
    active = ApplicationCase.create(owner_user_id="user_a", title="Active")
    gone = ApplicationCase.create(owner_user_id="user_a", title="Gone")
    gone._lifecycle_status = LifecycleStatus.DELETED.value
    db_session.add_all([active, gone])
    db_session.add_all(
        [
            CaseMembership.owner(case_id=active.id, user_id="user_a"),
            CaseMembership.owner(case_id=gone.id, user_id="user_a"),
        ]
    )
    db_session.commit()

    listed = {c.id for c in service.list_cases(db_session, user=as_user("user_a"))}
    assert active.id in listed
    assert gone.id not in listed


def test_get_case_never_serves_a_deleted_case(db_session: Session) -> None:
    # Construct a terminally-deleted case directly (the purge worker is a later slice).
    case = ApplicationCase.create(owner_user_id="user_a", title="Gone")
    case._lifecycle_status = LifecycleStatus.DELETED.value
    db_session.add(case)
    db_session.add(CaseMembership.owner(case_id=case.id, user_id="user_a"))
    db_session.commit()

    assert service.get_case(db_session, case_id=case.id, user=as_user("user_a")) is None
