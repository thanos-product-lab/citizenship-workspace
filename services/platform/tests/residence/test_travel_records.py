"""Travel records: manual create/edit/delete, versioning, tombstones, the ACTIVE gate.

Covers the Slice 2 acceptance: a manual trip is created as an ACTIVE record with an
immutable v1; editing appends a new version and never mutates the old one; removal is a
tombstone (not a hard delete) and is idempotency-guarded; date order is rejected at the
boundary; review_state and date_confidence stay independent; a stale revision conflicts;
a record from another of the user's cases is 404; a non-active case is refused; and the
event carries no movement detail.
"""

import uuid
from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.residence.domain import (
    DateConfidence,
    EntrySource,
    TravelRecord,
    TravelRecordVersion,
    TravelReviewState,
)
from app.shared.db import get_sessionmaker
from app.shared.records import DomainEventRecord, OutboxEventRecord
from app.shared.tenant import set_tenant

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}

# A confirmed, exact trip — the common manual entry.
TRIP = {
    "destination_label": "Spain",
    "destination_country_code": "ES",
    "departure_date": "2022-04-14",
    "return_date": "2022-04-26",
}


def _active_case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    assert (
        api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS).status_code
        == 200
    )
    confirmed = api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert confirmed.json()["lifecycle_status"] == "ACTIVE"
    return case_id


def _url(case_id: str) -> str:
    return f"/api/v1/cases/{case_id}/travel-records"


def test_adding_a_trip_creates_an_active_v1_record(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = api("user_a").post(_url(case_id), json=TRIP)
    assert resp.status_code == 201
    body = resp.json()
    assert body["version_number"] == 1
    assert body["entry_source"] == "MANUAL"
    assert body["lifecycle_status"] == "ACTIVE"
    assert body["date_confidence"] == "EXACT"  # defaults for a manual assertion
    assert body["review_state"] == "CONFIRMED"
    assert body["destination_country_code"] == "ES"
    assert body["revision"] == 2  # create + repoint bumps the token 1→2


def test_list_returns_active_records_in_departure_order(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    for dep, ret in [("2023-07-01", "2023-07-10"), ("2022-01-05", "2022-01-09")]:
        api("user_a").post(_url(case_id), json={**TRIP, "departure_date": dep, "return_date": ret})
    listed = api("user_a").get(_url(case_id)).json()
    assert [r["departure_date"] for r in listed] == ["2022-01-05", "2023-07-01"]


def test_editing_appends_an_immutable_version(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()

    edited = api("user_a").patch(
        f"{_url(case_id)}/{created['id']}",
        json={**TRIP, "return_date": "2022-04-27", "expected_revision": created["revision"]},
    )
    assert edited.status_code == 200
    assert edited.json()["version_number"] == 2
    assert edited.json()["return_date"] == "2022-04-27"

    versions = list(
        db_session.scalars(select(TravelRecordVersion).order_by(TravelRecordVersion.version_number))
    )
    # v1 is untouched (its return date is the original); v2 supersedes it.
    assert str(versions[0].return_date) == "2022-04-26"
    assert versions[1].supersedes_version_id == versions[0].id
    record = db_session.scalar(select(TravelRecord))
    assert record is not None
    assert record.current_version_id == versions[1].id


def test_removing_is_a_tombstone_not_a_hard_delete(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()

    removed = api("user_a").delete(
        f"{_url(case_id)}/{created['id']}", params={"expected_revision": created["revision"]}
    )
    assert removed.status_code == 200
    assert removed.json()["lifecycle_status"] == "REMOVED"

    # The row and its version survive; the list simply excludes the tombstone.
    assert db_session.scalar(select(func.count()).select_from(TravelRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(TravelRecordVersion)) == 1
    assert api("user_a").get(_url(case_id)).json() == []


def test_removing_twice_conflicts(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    api("user_a").delete(f"{_url(case_id)}/{created['id']}")
    again = api("user_a").delete(f"{_url(case_id)}/{created['id']}")
    assert again.status_code == 409  # IllegalTransition: already removed


def test_editing_a_removed_record_conflicts(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    api("user_a").delete(f"{_url(case_id)}/{created['id']}")
    edit = api("user_a").patch(f"{_url(case_id)}/{created['id']}", json=TRIP)
    assert edit.status_code == 409


def test_departure_after_return_is_rejected(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = api("user_a").post(
        _url(case_id), json={**TRIP, "departure_date": "2022-04-26", "return_date": "2022-04-14"}
    )
    assert resp.status_code == 422


def test_same_day_trip_is_allowed(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = api("user_a").post(
        _url(case_id), json={**TRIP, "departure_date": "2022-04-14", "return_date": "2022-04-14"}
    )
    assert resp.status_code == 201


def test_stale_revision_on_edit_conflicts(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    # A first edit moves the record on; a second with the stale revision conflicts.
    api("user_a").patch(
        f"{_url(case_id)}/{created['id']}",
        json={**TRIP, "notes": "first", "expected_revision": created["revision"]},
    )
    stale = api("user_a").patch(
        f"{_url(case_id)}/{created['id']}",
        json={**TRIP, "notes": "second", "expected_revision": created["revision"]},
    )
    assert stale.status_code == 409


def test_review_state_and_confidence_are_independent(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    a = (
        api("user_a")
        .post(_url(case_id), json={**TRIP, "review_state": "UNCERTAIN", "date_confidence": "EXACT"})
        .json()
    )
    b = (
        api("user_a")
        .post(
            _url(case_id),
            json={**TRIP, "review_state": "CONFIRMED", "date_confidence": "ESTIMATED"},
        )
        .json()
    )
    # The two axes do not collapse: each combination round-trips as entered (§6.1 gate).
    assert (a["review_state"], a["date_confidence"]) == ("UNCERTAIN", "EXACT")
    assert (b["review_state"], b["date_confidence"]) == ("CONFIRMED", "ESTIMATED")


def test_raw_trip_endpoints_are_stored_unclipped(api: Api, db_session: Session) -> None:
    # Trip 1 of the fixture straddles the qualifying-window start; M3A must store the
    # true endpoints and let the M3B rule clip — never bake a clipped value into the seed.
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id), json=TRIP)
    version = db_session.scalar(select(TravelRecordVersion))
    assert version is not None
    assert str(version.departure_date) == "2022-04-14"
    assert str(version.return_date) == "2022-04-26"


def test_a_record_from_another_case_is_not_found(api: Api) -> None:
    case_a = _active_case(api, "user_a")
    case_b = _active_case(api, "user_a")  # same user, different case
    created = api("user_a").post(_url(case_a), json=TRIP).json()

    # RLS lets user_a see both cases, so the case link is checked explicitly.
    assert api("user_a").patch(f"{_url(case_b)}/{created['id']}", json=TRIP).status_code == 404
    assert api("user_a").delete(f"{_url(case_b)}/{created['id']}").status_code == 404


def test_adding_on_a_non_active_case_is_a_domain_error_not_a_404(api: Api) -> None:
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "Draft"}).json()["id"])
    resp = api("user_a").post(_url(case_id), json=TRIP)
    assert resp.status_code == 409
    assert resp.json()["code"] == "CASE_NOT_ACTIVE"


def test_other_user_cannot_access_travel_records(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    assert api("user_b").get(_url(case_id)).status_code == 404
    assert api("user_b").post(_url(case_id), json=TRIP).status_code == 404
    assert api("user_b").patch(f"{_url(case_id)}/{created['id']}", json=TRIP).status_code == 404


def test_creating_emits_a_structural_event_without_movement_detail(
    api: Api, db_session: Session
) -> None:
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id), json=TRIP)

    event = db_session.scalar(
        select(DomainEventRecord).where(DomainEventRecord.event_type == "TravelRecordCreated")
    )
    assert event is not None
    payload = event.payload
    assert payload["version_number"] == 1
    assert payload["entry_source"] == "MANUAL"
    # The movement timeline stays out of the event stream (§38.1): no destination, dates.
    assert "Spain" not in str(payload)
    assert "2022-04-14" not in str(payload)

    outbox = db_session.scalar(
        select(func.count())
        .select_from(OutboxEventRecord)
        .where(OutboxEventRecord.event_type == "TravelRecordCreated")
    )
    assert outbox == 1


def test_removing_emits_a_removed_event(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    api("user_a").delete(f"{_url(case_id)}/{created['id']}")
    removed = db_session.scalar(
        select(func.count())
        .select_from(DomainEventRecord)
        .where(DomainEventRecord.event_type == "TravelRecordRemoved")
    )
    assert removed == 1


def test_db_check_rejects_reversed_dates_even_if_the_boundary_is_bypassed(
    api: Api, db_session: Session
) -> None:
    # The Pydantic validator normally stops this at 422; the CHECK is the backstop if a
    # future path ever bypasses it, so exercise it with a direct insert.
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    bad = TravelRecordVersion.build(
        travel_record_id=created["id"],
        version_number=2,
        destination_label="Nowhere",
        departure_date=date(2022, 4, 26),
        return_date=date(2022, 4, 14),
        date_confidence=DateConfidence.EXACT,
        review_state=TravelReviewState.CONFIRMED,
        entry_source=EntrySource.MANUAL,
        created_by="user_a",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_db_rejects_a_duplicate_version_number(api: Api, db_session: Session) -> None:
    # uq_travel_version_number: two versions of one record cannot share a number, even
    # if a future path appended one without bumping the parent's optimistic revision.
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    dup = TravelRecordVersion.build(
        travel_record_id=uuid.UUID(created["id"]),
        version_number=1,  # collides with the v1 the create already wrote
        destination_label="Spain",
        departure_date=date(2022, 4, 14),
        return_date=date(2022, 4, 26),
        date_confidence=DateConfidence.EXACT,
        review_state=TravelReviewState.CONFIRMED,
        entry_source=EntrySource.MANUAL,
        created_by="user_a",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_db_rejects_an_out_of_domain_enum_value(api: Api, db_session: Session) -> None:
    # ck_travel_version_review_state: the trust gate cannot be defeated by persisting a
    # review_state outside the domain enum, which a CONFIRMED comparison would miss.
    case_id = _active_case(api, "user_a")
    created = api("user_a").post(_url(case_id), json=TRIP).json()
    bad = TravelRecordVersion(
        id=uuid.uuid4(),
        travel_record_id=uuid.UUID(created["id"]),
        version_number=2,
        destination_label="Spain",
        departure_date=date(2022, 4, 14),
        return_date=date(2022, 4, 26),
        date_confidence="EXACT",
        review_state="BOGUS",  # not a TravelReviewState member
        entry_source="MANUAL",
        created_by="user_a",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_rls_hides_travel_records_from_another_tenant(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id), json=TRIP)

    other = get_sessionmaker()()
    try:
        set_tenant(other, "user_b")
        assert other.scalar(select(func.count()).select_from(TravelRecord)) == 0
        assert other.scalar(select(func.count()).select_from(TravelRecordVersion)) == 0

        set_tenant(other, "user_a")
        assert other.scalar(select(func.count()).select_from(TravelRecord)) == 1
    finally:
        other.close()
