"""A trip's reason, and the edit rule that keeps it from staling anything (ADR-0035).

The reason is on the stable record, so the assertions worth having are about what does
*not* happen: no version appended and no conclusion made stale when only the reason
changed, while a real date change still does both. And that the text never reaches the
event stream.
"""

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.residence.domain import (
    DateConfidence,
    EntrySource,
    TravelRecordFields,
    TravelRecordVersion,
    TravelReviewState,
    version_matches,
)
from app.shared.records import DomainEventRecord

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}

TRIP = {
    "destination_label": "Spain",
    "destination_country_code": "ES",
    "departure_date": "2023-06-01",
    "return_date": "2023-06-10",
}


def _assessed_case_with_trip(api: Api, user: str = "user_a") -> tuple[str, dict[str, object]]:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    trip = api(user).post(f"/api/v1/cases/{case_id}/travel-records", json=TRIP).json()
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    return case_id, trip


def _stale(api: Api, case_id: str) -> int:
    body = api("user_a").get(f"/api/v1/cases/{case_id}/overview").json()
    return int(body["stale"])


def _url(case_id: str, record_id: object = None) -> str:
    base = f"/api/v1/cases/{case_id}/travel-records"
    return f"{base}/{record_id}" if record_id else base


@pytest.mark.integration
def test_a_reason_is_saved_with_a_new_trip(api: Api) -> None:
    case_id, _ = _assessed_case_with_trip(api)
    created = api("user_a").post(
        _url(case_id),
        json={
            **TRIP,
            "departure_date": "2024-01-02",
            "return_date": "2024-01-09",
            "reason": "  Holiday  ",
        },
    )
    assert created.status_code == 201
    assert created.json()["reason"] == "Holiday"


@pytest.mark.integration
def test_changing_only_the_reason_appends_no_version_and_stales_nothing(
    api: Api, db_session: Session
) -> None:
    case_id, trip = _assessed_case_with_trip(api)
    assert _stale(api, case_id) == 0

    edited = api("user_a").patch(
        _url(case_id, trip["id"]),
        json={**TRIP, "reason": "Visiting family", "expected_revision": trip["revision"]},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["reason"] == "Visiting family"
    assert body["version_number"] == 1
    # The record changed, so its concurrency token moved: a second tab holding the old
    # revision is refused rather than silently overwriting the reason.
    assert body["revision"] > trip["revision"]
    assert _stale(api, case_id) == 0

    versions = db_session.scalar(select(func.count()).select_from(TravelRecordVersion))
    assert versions == 1


@pytest.mark.integration
def test_a_date_change_still_appends_a_version_and_stales(api: Api) -> None:
    case_id, trip = _assessed_case_with_trip(api)
    edited = (
        api("user_a")
        .patch(
            _url(case_id, trip["id"]),
            json={
                **TRIP,
                "return_date": "2023-06-12",
                "reason": "Holiday",
                "expected_revision": trip["revision"],
            },
        )
        .json()
    )
    assert edited["version_number"] == 2
    assert edited["reason"] == "Holiday"
    assert _stale(api, case_id) > 0


@pytest.mark.integration
def test_saving_the_form_unchanged_writes_nothing(api: Api, db_session: Session) -> None:
    case_id, trip = _assessed_case_with_trip(api)
    edited = (
        api("user_a")
        .patch(_url(case_id, trip["id"]), json={**TRIP, "expected_revision": trip["revision"]})
        .json()
    )
    assert edited["version_number"] == 1
    assert edited["revision"] == trip["revision"]
    assert _stale(api, case_id) == 0
    events = db_session.scalar(
        select(func.count())
        .select_from(DomainEventRecord)
        .where(
            DomainEventRecord.event_type.in_(
                ("TravelRecordVersionCreated", "TravelRecordReasonChanged")
            )
        )
    )
    assert events == 0


@pytest.mark.integration
def test_leaving_the_reason_out_keeps_it_and_null_clears_it(api: Api) -> None:
    case_id, trip = _assessed_case_with_trip(api)
    first = (
        api("user_a")
        .patch(
            _url(case_id, trip["id"]),
            json={**TRIP, "reason": "Holiday", "expected_revision": trip["revision"]},
        )
        .json()
    )

    # A client that predates the reason sends the version fields only.
    kept = (
        api("user_a")
        .patch(
            _url(case_id, trip["id"]),
            json={**TRIP, "return_date": "2023-06-11", "expected_revision": first["revision"]},
        )
        .json()
    )
    assert kept["reason"] == "Holiday"

    cleared = (
        api("user_a")
        .patch(
            _url(case_id, trip["id"]),
            json={
                **TRIP,
                "return_date": "2023-06-11",
                "reason": None,
                "expected_revision": kept["revision"],
            },
        )
        .json()
    )
    assert cleared["reason"] is None


@pytest.mark.integration
def test_the_reason_is_audited_but_never_in_the_event(api: Api, db_session: Session) -> None:
    case_id, trip = _assessed_case_with_trip(api)
    api("user_a").patch(
        _url(case_id, trip["id"]),
        json={**TRIP, "reason": "Grandmother's funeral", "expected_revision": trip["revision"]},
    )
    event = db_session.scalar(
        select(DomainEventRecord).where(DomainEventRecord.event_type == "TravelRecordReasonChanged")
    )
    assert event is not None
    assert "funeral" not in str(event.payload)


@pytest.mark.integration
def test_a_reason_over_the_limit_is_refused(api: Api) -> None:
    case_id, _ = _assessed_case_with_trip(api)
    resp = api("user_a").post(_url(case_id), json={**TRIP, "reason": "x" * 201})
    assert resp.status_code == 422


# --- the rule the edit command rests on ------------------------------------------------

_fields = st.builds(
    TravelRecordFields,
    destination_label=st.sampled_from(["Spain", "France", "Côte d'Ivoire"]),
    departure_date=st.dates(date(2020, 1, 1), date(2026, 12, 31)),
    return_date=st.just(date(2027, 1, 1)),
    date_confidence=st.sampled_from(list(DateConfidence)),
    review_state=st.sampled_from(list(TravelReviewState)),
    destination_country_code=st.sampled_from([None, "ES", "FR"]),
    notes=st.sampled_from([None, "", "left early"]),
)


def _version_of(fields: TravelRecordFields) -> TravelRecordVersion:
    import uuid

    return TravelRecordVersion.build(
        travel_record_id=uuid.uuid4(),
        version_number=1,
        destination_label=fields.destination_label,
        departure_date=fields.departure_date,
        return_date=fields.return_date,
        date_confidence=fields.date_confidence,
        review_state=fields.review_state,
        entry_source=EntrySource.MANUAL,
        created_by="user",
        destination_country_code=fields.destination_country_code,
        notes=fields.notes,
    )


@pytest.mark.property
@given(_fields)
def test_the_same_fields_always_match_their_own_version(fields: TravelRecordFields) -> None:
    """The half that lets a reason-only edit through without a version."""
    assert version_matches(_version_of(fields), fields)


@pytest.mark.property
@given(
    _fields,
    st.sampled_from(["label", "departure", "return", "confidence", "review", "code", "notes"]),
)
def test_any_version_field_change_is_a_mismatch(fields: TravelRecordFields, which: str) -> None:
    """The half that keeps staleness honest: a change to anything a rule could read is
    never mistaken for an unchanged save, so it always appends a version and stales."""
    version = _version_of(fields)
    changed = {
        "label": lambda f: f.__class__(
            **{**vars(f), "destination_label": f.destination_label + "x"}
        ),
        "departure": lambda f: f.__class__(
            **{**vars(f), "departure_date": f.departure_date - timedelta(days=1)}
        ),
        "return": lambda f: f.__class__(
            **{**vars(f), "return_date": f.return_date + timedelta(days=1)}
        ),
        "confidence": lambda f: f.__class__(
            **{
                **vars(f),
                "date_confidence": next(c for c in DateConfidence if c is not f.date_confidence),
            }
        ),
        "review": lambda f: f.__class__(
            **{
                **vars(f),
                "review_state": next(r for r in TravelReviewState if r is not f.review_state),
            }
        ),
        "code": lambda f: f.__class__(
            **{
                **vars(f),
                "destination_country_code": "IT" if f.destination_country_code != "IT" else None,
            }
        ),
        "notes": lambda f: f.__class__(**{**vars(f), "notes": (f.notes or "") + "!"}),
    }[which](fields)
    assert not version_matches(version, changed)
