"""Deleting a document (Domain §51.1).

The command is four of the seven steps in one transaction; the purge is the other two,
asynchronously. What these tests hold is the boundary between them — because the failure
mode this slice exists to prevent is not "deletion does not work", it is "deletion works
and something that depended on the document goes on looking confident".
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorage, get_storage
from app.evidence.domain import (
    EvidenceItem,
    EvidenceLifecycleStatus,
    EvidenceTravelLink,
    LinkAvailability,
)
from tests.evidence.conftest import fixture_bytes as _fixture
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _case_with_trip(api: Api, user: str, *, title: str = "Deletion") -> tuple[str, str]:
    case_id = str(api(user).post("/api/v1/cases", json={"title": title}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    trip = api(user).post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Greece",
            "destination_country_code": "GR",
            "departure_date": "2024-06-05",
            "return_date": "2024-07-15",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )
    return case_id, str(trip.json()["id"])


def _document(api: Api, user: str, case_id: str, *, name: str = "Athens booking") -> str:
    content = _fixture("travel-booking.pdf")
    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": len(content)},
        )
        .json()
    )
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(str(grant["upload_fields"]["key"]), content)
    item = api(user).post(
        f"/api/v1/cases/{case_id}/evidence",
        json={
            "upload_token": grant["upload_token"],
            "category": "TRAVEL_SUPPORT",
            "display_name": name,
            "original_filename": "booking.pdf",
        },
    )
    return str(item.json()["id"])


def _currency(api: Api, case_id: str) -> dict[str, str]:
    rows = api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    return {row["requirement_key"]: row["currency"] for row in rows}


# --- what the user sees immediately -------------------------------------------------


def test_a_deleted_document_stops_being_reachable_at_once(api: Api, db_session: Session) -> None:
    """§51.1 step 1. Not "eventually, once the purge runs" — the bytes may take a moment to
    go, but the user is told the document is gone the instant they ask for it to be."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    assert api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 204

    assert api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 404
    assert (
        api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}/content").status_code == 404
    )
    library = api("user_a").get(f"/api/v1/cases/{case_id}/evidence").json()
    assert library["items"] == []


def test_deleting_twice_is_a_conflict_not_a_second_deletion(api: Api, db_session: Session) -> None:
    """The first call dispatched a purge. Answering 204 again would imply a second one is
    safe, and a second purge is a second attempt to destroy bytes that are already gone."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    second = api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    # 404, not 409: the item is already unreachable, so the command cannot find it to
    # refuse it — and an id must not confirm that something exists in a state it is not in.
    assert second.status_code == 404


def test_a_retry_cannot_be_asked_for_on_a_deleted_document(api: Api, db_session: Session) -> None:
    """§14.5: "a deleted evidence item cannot be reprocessed"."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    assert (
        api("user_a").post(f"/api/v1/cases/{case_id}/evidence/{item_id}/retry").status_code == 404
    )


def test_another_tenant_cannot_delete(api: Api, db_session: Session) -> None:
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    assert api("user_b").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 404

    # Through the owner's own API rather than the shared session: the point is that the
    # document is still there and still usable, which is what user_a can see.
    still_there = api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    assert still_there.status_code == 200
    assert still_there.json()["lifecycle_status"] == "ACTIVE"


# --- what it does to the assessment -------------------------------------------------


def test_deleting_a_document_withdraws_its_support_and_stales_the_verdict(
    api: Api, db_session: Session
) -> None:
    """Steps 4 and 5, and the reason this slice exists.

    A conclusion drawn while a document supported a trip must not go on standing unchanged
    once the document is gone. And the absence totals must not move: deleting a booking
    does not change how many days the user was abroad.
    """
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _currency(api, case_id)["residence.travel_consistency"] == "CURRENT"

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    after = _currency(api, case_id)
    assert after["residence.travel_consistency"] == "STALE"
    assert after["residence.total_absences"] == "CURRENT"
    assert after["residence.final_year_absences"] == "CURRENT"

    db_session.expire_all()
    link = db_session.execute(
        select(EvidenceTravelLink).where(EvidenceTravelLink.case_id == uuid.UUID(case_id))
    ).scalar_one()
    # DELETED, not UNAVAILABLE: the document is gone, not merely detached from the trip.
    assert link.availability is LinkAvailability.DELETED


def test_the_stale_reason_names_the_documents(api: Api, db_session: Session) -> None:
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    detail = (
        api("user_a")
        .get(f"/api/v1/cases/{case_id}/requirements/residence.travel_consistency")
        .json()
    )
    assert detail["stale"]["reason_code"] == "EVIDENCE_SUPPORT_CHANGED"


def test_deleting_a_document_that_supported_nothing_stales_nothing(
    api: Api, db_session: Session
) -> None:
    """`mark_support_unavailable` skips invalidation when no link moved. A document nobody
    attached to anything cannot have influenced a conclusion, and staling the case for it
    would be over-firing — the user would be told to recheck work that did not change."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    assert _currency(api, case_id)["residence.travel_consistency"] == "CURRENT"


def test_the_deletion_event_carries_no_storage_key_or_name(api: Api, db_session: Session) -> None:
    """§38.1's payload rule, and the point of a tombstone. `domain_events` is immutable, so
    a name or a key written there outlives the deletion meant to remove it."""
    from app.shared.records import DomainEventRecord

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id, name="Amara's Athens booking")
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    db_session.expire_all()
    event = db_session.execute(
        select(DomainEventRecord).where(DomainEventRecord.event_type == "EvidenceDeleted")
    ).scalar_one()
    rendered = str(event.payload)
    assert "Athens" not in rendered
    assert "booking.pdf" not in rendered
    assert "storage_key" not in rendered


# --- the aggregate's own rules ------------------------------------------------------


def test_the_transitions_refuse_out_of_order() -> None:
    """Unit-level, because HTTP cannot reach these guards.

    Every route resolves an item through `get_active_for_case`, which excludes non-ACTIVE
    rows, so a second delete is a 404 before any transition is attempted — mutating the
    guards away turns no integration test red. That makes them untested rather than
    unnecessary: the purge and any future caller reach the aggregate directly, and
    `mark_deleted` in particular must never run on an item whose access was never blocked.
    """
    from app.evidence.domain import EvidenceCategory, utcnow
    from app.shared.errors import IllegalTransition

    item = EvidenceItem.uploaded(
        case_id=uuid.uuid4(),
        category=EvidenceCategory.TRAVEL_SUPPORT,
        display_name="A booking",
        created_by="user_a",
    )
    at = utcnow()

    # A document whose access was never blocked cannot be marked deleted.
    with pytest.raises(IllegalTransition):
        item.mark_deleted(at=at)

    item.request_deletion(at=at)
    # Comparing `.value` rather than using `is`: an identity assertion narrows the property
    # for mypy, and the narrowing does not widen again when `mark_deleted` mutates it — so
    # the DELETED check below reads as unreachable code.
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETION_PENDING.value
    assert item.deleted_at is None, "not deleted yet — the bytes are still there"

    # And it cannot be requested twice.
    with pytest.raises(IllegalTransition):
        item.request_deletion(at=at)

    item.mark_deleted(at=at)
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETED.value
    assert item.deleted_at == at
