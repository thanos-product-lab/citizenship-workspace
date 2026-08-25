"""Attaching a document to a trip (Domain §11.9, ADR-0021).

What a link is, what it refuses, and — the part that matters — what it must and must not
invalidate. The invalidation tests live here rather than in `tests/assessments/` because
the thing under test is the *command*, and a dependency declared but never fired is
indistinguishable from one never declared at all until something asks.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorage, get_storage
from app.evidence.domain import EvidenceTravelLink, LinkAvailability
from tests.evidence.conftest import fixture_bytes as _fixture
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _case_with_trip(api: Api, user: str, *, title: str = "Links") -> tuple[str, str]:
    """An active case with one confirmed trip. Returns (case_id, travel_record_id)."""
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


def _links(session: Session, case_id: str) -> list[EvidenceTravelLink]:
    stmt = select(EvidenceTravelLink).where(EvidenceTravelLink.case_id == uuid.UUID(case_id))
    return list(session.execute(stmt).scalars())


# --- the capability ---------------------------------------------------------------


def test_a_document_can_support_a_trip(api: Api, db_session: Session) -> None:
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    assert response.status_code == 200
    assert response.json()["supporting_evidence_item_ids"] == [item_id]
    # And the trip says so on the next read, not only in the command's own answer.
    listed = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    assert listed[0]["supporting_evidence_item_ids"] == [item_id]


def test_detaching_leaves_the_link_row_behind(api: Api, db_session: Session) -> None:
    """§22.3: a historical assessment linked this row and has to keep resolving to
    something that can say what it read *and* that it is no longer available. Deleting
    the row would leave the provenance graph with a dangling id."""
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    response = api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence/{item_id}"
    )

    assert response.status_code == 200
    assert response.json()["supporting_evidence_item_ids"] == []
    db_session.expire_all()
    rows = _links(db_session, case_id)
    assert len(rows) == 1, "the row is kept; only its availability changes"
    assert rows[0].availability is LinkAvailability.UNAVAILABLE
    assert rows[0].unlinked_at is not None


def test_a_document_can_be_reattached_after_being_detached(api: Api, db_session: Session) -> None:
    """The unique index is partial (`WHERE availability = 'AVAILABLE'`) precisely so this
    works. A plain unique index would have let a user detach a booking once and never
    attach it again — the row is still there, and nothing in the UI would explain why."""
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    path = f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence"

    api("user_a").post(path, json={"evidence_item_id": item_id})
    api("user_a").delete(f"{path}/{item_id}")
    again = api("user_a").post(path, json={"evidence_item_id": item_id})

    assert again.status_code == 200
    assert again.json()["supporting_evidence_item_ids"] == [item_id]


def test_attaching_twice_changes_nothing_and_says_so(api: Api, db_session: Session) -> None:
    """The user asked for a state that already holds. Emitting a second event would put a
    lie in `domain_events` — the document was not attached twice — and restale a result
    for a change that did not happen."""
    from app.shared.records import DomainEventRecord

    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    path = f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence"

    api("user_a").post(path, json={"evidence_item_id": item_id})
    api("user_a").post(path, json={"evidence_item_id": item_id})

    db_session.expire_all()
    events = db_session.execute(
        select(DomainEventRecord).where(
            DomainEventRecord.event_type == "EvidenceAttachedToTravelRecord"
        )
    ).scalars()
    assert len(list(events)) == 1
    assert len(_links(db_session, case_id)) == 1


# --- what it refuses --------------------------------------------------------------


def test_a_document_from_another_case_cannot_support_this_trip(
    api: Api, db_session: Session
) -> None:
    """The same user, two of their own cases. RLS does not help here — both cases are
    theirs — so the case boundary is checked in the command, and a link is exactly the
    shape that could otherwise smuggle a row across it."""
    case_id, trip_id = _case_with_trip(api, "user_a", title="Mine")
    other_case, _ = _case_with_trip(api, "user_a", title="Also mine")
    foreign_item = _document(api, "user_a", other_case)

    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": foreign_item},
    )

    # 404, not 403: an id must not confirm that something exists somewhere else.
    assert response.status_code == 404
    assert _links(db_session, case_id) == []


def test_another_tenants_trip_is_not_reachable(api: Api, db_session: Session) -> None:
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    response = api("user_b").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    assert response.status_code == 404


def test_a_document_still_being_read_cannot_be_attached(api: Api, db_session: Session) -> None:
    """Not a judgement on the document — it may well succeed. But coverage would settle
    underneath the user seconds later, and a support state that changes on its own is one
    nobody can act on."""
    from app.evidence.domain import EvidenceItem, EvidenceProcessingStatus

    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    item = db_session.get(EvidenceItem, uuid.UUID(item_id))
    assert item is not None
    item.processing_status = EvidenceProcessingStatus.EXTRACTING_TEXT.value
    db_session.commit()

    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EVIDENCE_NOT_ATTACHABLE"


def test_a_document_that_could_not_be_read_can_still_be_attached(
    api: Api, db_session: Session
) -> None:
    """The other half, and the more interesting one. A user may know perfectly well what
    is in a scan the parser could not read. The link is their assertion about their own
    document, not the machine's verdict on it — making extraction success a precondition
    for saying "this is my booking" would let a parser failure silently become a coverage
    gap the user cannot close."""
    from app.evidence.domain import EvidenceItem, EvidenceProcessingStatus

    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    item = db_session.get(EvidenceItem, uuid.UUID(item_id))
    assert item is not None
    item.processing_status = EvidenceProcessingStatus.PARTIALLY_COMPLETED.value
    db_session.commit()

    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    assert response.status_code == 200


def test_detaching_something_that_was_never_attached_is_an_error(
    api: Api, db_session: Session
) -> None:
    """Unlike attach, a no-op here is not "your intent already holds" — it means the
    caller's picture of the case is wrong, and 200 would confirm a state never true."""
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    response = api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence/{item_id}"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EVIDENCE_LINK_NOT_FOUND"


def test_a_removed_trip_cannot_be_evidenced(api: Api, db_session: Session) -> None:
    """A removed trip is excluded from every total and every rule, so a link on it would
    be one no assessment ever reads — and a support state on a row the user deleted."""
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{trip_id}")

    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    assert response.status_code == 404


# --- the RLS boundary -------------------------------------------------------------
#
# Not here. `evidence_travel_links` is registered in `tests/security/conftest.py`'s
# `CASE_SCOPED_TABLES`, so `test_rls_matrix.py` covers it with the same four properties it
# applies to every case-scoped table — invisible to another tenant, refuses their write,
# accepts the owner's, and fails closed with no tenant set. Its write-rejection assertion
# checks the *message*, not just the exception type, which a hand-rolled test here got
# wrong twice: an `INSERT ... SELECT` run as the intruder inserts zero rows, because the
# intruder cannot see the source rows to select them, and no policy is ever violated.
#
# Every test above goes through a route that checks ownership itself, so all of them would
# still pass with the policy dropped. That is what the matrix suite is for.
