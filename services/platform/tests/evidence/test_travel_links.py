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


# --- what a link change invalidates -------------------------------------------------


def _currency(api: Api, case_id: str) -> dict[str, str]:
    rows = api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    return {row["requirement_key"]: row["currency"] for row in rows}


def test_attaching_a_document_stales_the_consistency_verdict_only(
    api: Api, db_session: Session
) -> None:
    """The fan-out, end to end, and both halves are the test.

    Attaching **must** stale `residence.travel_consistency`: the rule reads coverage, so a
    coverage change under a CURRENT result would leave a stale result being returned as
    current (CLAUDE.md §9).

    It **must not** stale the absence totals. Attaching a booking does not change how many
    days the user was outside the UK — it changes how well supported their own account of
    it is. The unit-level version of this property is in
    `test_selective_invalidation.py`; this one proves the command actually fires it, which
    a declaration alone never shows.
    """
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _currency(api, case_id)["residence.travel_consistency"] == "CURRENT"

    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    after = _currency(api, case_id)
    assert after["residence.travel_consistency"] == "STALE"
    assert after["residence.total_absences"] == "CURRENT"
    assert after["residence.final_year_absences"] == "CURRENT"
    assert after["residence.physical_presence_start_date"] == "CURRENT"


def test_detaching_a_document_stales_it_too(api: Api, db_session: Session) -> None:
    """The direction that matters most for the trust model. Removing support must not
    leave a conclusion standing that was drawn while the support existed — that is
    "quietly confident", which is the failure this whole product is built against."""
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    path = f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence"
    api("user_a").post(path, json={"evidence_item_id": item_id})
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _currency(api, case_id)["residence.travel_consistency"] == "CURRENT"

    api("user_a").delete(f"{path}/{item_id}")

    after = _currency(api, case_id)
    assert after["residence.travel_consistency"] == "STALE"
    assert after["residence.total_absences"] == "CURRENT"


def test_the_stale_reason_says_it_was_the_documents(api: Api, db_session: Session) -> None:
    """`EVIDENCE_SUPPORT_CHANGED`, not `TRAVEL_RECORD_CHANGED`. The user is shown this
    sentence, and telling them their travel records changed when they attached a document
    would send them to check dates they never touched."""
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    consistency = (
        api("user_a")
        .get(f"/api/v1/cases/{case_id}/requirements/residence.travel_consistency")
        .json()
    )
    stale = consistency["stale"]
    assert stale["reason_code"] == "EVIDENCE_SUPPORT_CHANGED"
    assert "documents attached" in stale["reason"]


def test_a_recalculation_records_the_links_it_read(api: Api, db_session: Session) -> None:
    """Provenance reaches the database, not only the evaluator's return value: a trusted
    result must reference the exact inputs behind it (directive 5)."""
    from app.assessments.domain import AssessmentInputLink, AssessmentResult
    from app.requirements.models import RequirementDefinition

    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.expire_all()
    links = db_session.execute(
        select(AssessmentInputLink)
        .join(AssessmentResult, AssessmentResult.id == AssessmentInputLink.assessment_result_id)
        .join(RequirementDefinition, RequirementDefinition.id == AssessmentResult.requirement_id)
        .where(
            RequirementDefinition.requirement_key == "residence.travel_consistency",
            AssessmentInputLink.input_kind == "EVIDENCE_LINK",
            AssessmentResult.case_id == uuid.UUID(case_id),
        )
    ).scalars()
    recorded = [link.input_version_id for link in links]
    stored = _links(db_session, case_id)
    assert recorded == [stored[0].id], "the link row itself is the input, not the document"


def test_removing_a_trip_withdraws_the_documents_attached_to_it(
    api: Api, db_session: Session
) -> None:
    """Otherwise the links stay AVAILABLE on a trip no rule can see.

    No conclusion was wrong — a removed record is excluded from `trips`, so the rule never
    counted it. What was wrong was the provenance: every later result recorded an
    `EVIDENCE_LINK` for a trip the assessment does not contain, and the panel resolved it
    to "Document for <the removed trip>" marked still current. The one surface whose job
    is saying what a conclusion rested on was asserting support from a record that no
    longer exists.

    `UNAVAILABLE`, not `DELETED`: the document is fine and still in the library.
    """
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )

    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{trip_id}")

    db_session.expire_all()
    rows = _links(db_session, case_id)
    assert len(rows) == 1, "the row is kept, as it is for any other withdrawal"
    assert rows[0].availability is LinkAvailability.UNAVAILABLE
    assert rows[0].unlinked_at is not None

    # The document itself is untouched — it is still in the library, attachable elsewhere.
    library = api("user_a").get(f"/api/v1/cases/{case_id}/evidence").json()
    assert [item["id"] for item in library["items"]] == [item_id]


def test_a_recalculation_after_removing_a_trip_records_no_link_for_it(
    api: Api, db_session: Session
) -> None:
    """The consequence the previous test protects, asserted where it is visible."""
    from app.assessments.domain import AssessmentInputLink, AssessmentResult
    from app.requirements.models import RequirementDefinition

    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{trip_id}")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.expire_all()
    links = db_session.execute(
        select(AssessmentInputLink)
        .join(AssessmentResult, AssessmentResult.id == AssessmentInputLink.assessment_result_id)
        .join(RequirementDefinition, RequirementDefinition.id == AssessmentResult.requirement_id)
        .where(
            RequirementDefinition.requirement_key == "residence.travel_consistency",
            AssessmentInputLink.input_kind == "EVIDENCE_LINK",
            AssessmentResult.case_id == uuid.UUID(case_id),
            AssessmentResult.currency == "CURRENT",
        )
    ).scalars()
    assert list(links) == []


def test_withdrawing_a_removed_trips_links_is_recorded_in_the_history(
    api: Api, db_session: Session
) -> None:
    """`domain_events` is the record of what happened to the case, and a link ending is a
    thing that happened. `availability` alone says neither when nor why, so someone
    reconstructing a conclusion change would find a withdrawn link and no account of it."""
    from app.shared.records import DomainEventRecord

    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{trip_id}")

    db_session.expire_all()
    detached = db_session.execute(
        select(DomainEventRecord).where(
            DomainEventRecord.event_type == "EvidenceDetachedFromTravelRecord"
        )
    ).scalars()
    payloads = [event.payload for event in detached]
    assert len(payloads) == 1
    assert payloads[0]["availability"] == "UNAVAILABLE"
    assert payloads[0]["travel_record_id"] == trip_id
