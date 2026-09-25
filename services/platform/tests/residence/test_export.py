"""The travel list to hand over (ADR-0035).

Pure rules first: which trips are in the period, in what order, marked how. Then the CSV,
where user text meets a spreadsheet. Then the API, which must list what the assessment sees.
"""

import csv
import io
import uuid
from collections.abc import Callable
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from app.requirements.rules_core import qualifying_window
from app.residence.export import (
    CSV_HEADERS,
    ExportCaution,
    ExportScope,
    ExportTripInput,
    TravelExport,
    TripMarker,
    build_export,
    to_csv,
)

APPLICATION_DATE = date(2027, 4, 15)
WINDOW = qualifying_window(APPLICATION_DATE)  # 16 April 2022 to 15 April 2027
TODAY = date(2026, 9, 24)


def _trip(
    departure: date,
    return_: date,
    *,
    label: str = "Spain",
    # A reason by default, as a finished list has; tests about a missing one pass None.
    reason: str | None = "Holiday",
    review_state: str = "CONFIRMED",
    date_confidence: str = "EXACT",
) -> ExportTripInput:
    return ExportTripInput(
        travel_record_id=uuid.uuid4(),
        destination_label=label,
        reason=reason,
        departure_date=departure,
        return_date=return_,
        review_state=review_state,
        date_confidence=date_confidence,
    )


def _export(
    *trips: ExportTripInput,
    awaiting: int = 0,
    application_date: date | None = APPLICATION_DATE,
) -> TravelExport:
    return build_export(
        trips=trips,
        application_date=application_date,
        documents_awaiting_review=awaiting,
        prepared_on=TODAY,
    )


# --- the period -----------------------------------------------------------------------


def test_the_period_is_the_qualifying_window() -> None:
    assert WINDOW.start == date(2022, 4, 16)
    assert _export().window == WINDOW


def test_a_trip_straddling_the_start_is_listed() -> None:
    """Abroad across the first day of the period: the form asks about it, even though only
    part of it is counted."""
    straddling = _trip(date(2022, 4, 10), date(2022, 4, 20))
    assert [t.departure_date for t in _export(straddling).trips] == [date(2022, 4, 10)]


def test_a_trip_ending_the_day_before_the_period_is_not() -> None:
    before = _trip(date(2022, 4, 1), date(2022, 4, 15))
    assert _export(before).trips == ()


def test_a_trip_returning_on_the_first_day_is_listed() -> None:
    """Zero days counted (the return day is in the UK, RULES_SPEC §5), still a trip."""
    returning = _trip(date(2022, 4, 1), date(2022, 4, 16))
    assert len(_export(returning).trips) == 1


def test_a_same_day_trip_is_listed() -> None:
    day_trip = _trip(date(2024, 3, 3), date(2024, 3, 3))
    assert len(_export(day_trip).trips) == 1


def test_without_an_application_date_every_trip_is_listed_and_it_says_why() -> None:
    before = _trip(date(2019, 1, 1), date(2019, 1, 5))
    export = _export(before, application_date=None)
    assert export.scope is ExportScope.ALL
    assert export.window is None
    assert len(export.trips) == 1
    assert [c.code for c in export.cautions] == [ExportCaution.NO_APPLICATION_DATE]


def test_trips_are_listed_in_departure_order() -> None:
    later = _trip(date(2025, 1, 1), date(2025, 1, 9), label="Italy")
    earlier = _trip(date(2023, 1, 1), date(2023, 1, 9), label="France")
    assert [t.destination_label for t in _export(later, earlier).trips] == ["France", "Italy"]


@pytest.mark.property
@given(
    st.dates(date(2020, 2, 28), date(2032, 3, 1)),
    st.dates(date(2014, 1, 1), date(2032, 12, 31)),
    st.integers(0, 60),
)
def test_a_trip_is_listed_exactly_when_its_dates_touch_the_period(
    application_date: date, departure: date, length: int
) -> None:
    """Over leap days and year ends: calendar overlap with [start, end], both inclusive."""
    trip = _trip(departure, departure + timedelta(days=length))
    window = qualifying_window(application_date)
    listed = bool(_export(trip, application_date=application_date).trips)
    assert listed == (trip.departure_date <= window.end and trip.return_date >= window.start)


# --- what a trip is marked with ------------------------------------------------------


def test_a_counted_trip_carries_no_marker() -> None:
    assert _export(_trip(date(2023, 1, 1), date(2023, 1, 9))).trips[0].markers == ()


@pytest.mark.parametrize(
    ("review_state", "date_confidence", "expected"),
    [
        ("CONFIRMED", "ESTIMATED", (TripMarker.ESTIMATED,)),
        ("CONFIRMED", "UNKNOWN", (TripMarker.ESTIMATED,)),
        ("DRAFT", "EXACT", (TripMarker.NOT_CONFIRMED,)),
        ("UNCERTAIN", "ESTIMATED", (TripMarker.NOT_CONFIRMED, TripMarker.ESTIMATED)),
        ("CONFIRMED", "CONFLICTING", (TripMarker.DISPUTED,)),
    ],
)
def test_a_held_back_trip_is_listed_and_marked(
    review_state: str, date_confidence: str, expected: tuple[TripMarker, ...]
) -> None:
    """Listed, not left out: leaving a trip off a list handed to the Home Office is the
    dangerous direction (CLAUDE.md §2.7)."""
    trip = _trip(
        date(2023, 1, 1),
        date(2023, 1, 9),
        review_state=review_state,
        date_confidence=date_confidence,
    )
    assert _export(trip).trips[0].markers == expected


# --- cautions -----------------------------------------------------------------------


def test_overlapping_trips_are_named_before_relying_on_the_list() -> None:
    a = _trip(date(2023, 1, 1), date(2023, 1, 10))
    b = _trip(date(2023, 1, 5), date(2023, 1, 15))
    c = _trip(date(2024, 1, 1), date(2024, 1, 5))
    cautions = _export(a, b, c).cautions
    assert [(x.code, x.count) for x in cautions] == [(ExportCaution.OVERLAPPING_TRIPS, 2)]


def test_trips_meeting_on_a_travel_day_do_not_overlap() -> None:
    """Returning and leaving again on the same day shares no day abroad (RULES_SPEC §5)."""
    a = _trip(date(2023, 1, 1), date(2023, 1, 10))
    b = _trip(date(2023, 1, 10), date(2023, 1, 15))
    assert _export(a, b).cautions == ()


def test_trips_without_a_reason_are_named_before_handing_the_list_over() -> None:
    """The application form asks for a reason for every trip (ADR-0035). The list says how
    many are missing; it does not leave them out, and it does not refuse to be built."""
    export = _export(
        _trip(date(2023, 1, 1), date(2023, 1, 9), reason=None),
        _trip(date(2023, 3, 1), date(2023, 3, 9), reason=""),
        _trip(date(2023, 5, 1), date(2023, 5, 9)),
    )
    assert len(export.trips) == 3
    assert [(c.code, c.count) for c in export.cautions] == [(ExportCaution.MISSING_REASONS, 2)]


def test_a_trip_outside_the_period_is_not_counted_as_missing_a_reason() -> None:
    """Only the listed trips need one: a trip before the period is not on the list."""
    before = _trip(date(2019, 1, 1), date(2019, 1, 5), reason=None)
    assert _export(before).cautions == ()


def test_documents_awaiting_review_are_named() -> None:
    cautions = _export(awaiting=2).cautions
    assert [(x.code, x.count) for x in cautions] == [(ExportCaution.DOCUMENTS_AWAITING_REVIEW, 2)]


# --- CSV ----------------------------------------------------------------------------


def _rows(text: str) -> list[list[str]]:
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def test_the_csv_is_shaped_like_the_form() -> None:
    export = _export(
        _trip(date(2023, 1, 1), date(2023, 1, 9), label="France", reason="Holiday"),
        _trip(date(2023, 3, 1), date(2023, 3, 9), date_confidence="ESTIMATED", reason=None),
    )
    rows = _rows(to_csv(export, lambda m: m.value))
    assert tuple(rows[0]) == CSV_HEADERS
    assert rows[1] == ["France", "Holiday", "2023-01-01", "2023-01-09", ""]
    assert rows[2] == ["Spain", "", "2023-03-01", "2023-03-09", "ESTIMATED"]


@pytest.mark.parametrize("hostile", ["=SUM(1,2)", "+44 20 7946 0000", "-1", "@cmd", "\tx"])
def test_a_cell_a_spreadsheet_would_run_is_made_text(hostile: str) -> None:
    export = _export(_trip(date(2023, 1, 1), date(2023, 1, 9), label=hostile, reason=hostile))
    row = _rows(to_csv(export, lambda m: m.value))[1]
    assert row[0] == f"'{hostile}"
    assert row[1] == f"'{hostile}"


def test_commas_quotes_and_accents_survive() -> None:
    label = 'Côte d\'Ivoire, "Abidjan"'
    export = _export(_trip(date(2023, 1, 1), date(2023, 1, 9), label=label))
    assert _rows(to_csv(export, lambda m: m.value))[1][0] == label


# --- API ----------------------------------------------------------------------------

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


def _case(api: Api, *, with_date: bool = True) -> str:
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    if with_date:
        api("user_a").post(
            f"/api/v1/cases/{case_id}/application-dates/select",
            json={"application_date": "2027-04-15"},
        )
    return case_id


def _add(api: Api, case_id: str, **trip: object) -> dict[str, object]:
    body = {
        "destination_label": "Spain",
        "departure_date": "2023-06-01",
        "return_date": "2023-06-10",
        **trip,
    }
    resp = api("user_a").post(f"/api/v1/cases/{case_id}/travel-records", json=body)
    assert resp.status_code == 201, resp.text
    result: dict[str, object] = resp.json()
    return result


@pytest.mark.integration
def test_the_export_lists_the_period_with_reasons_and_markers(api: Api) -> None:
    case_id = _case(api)
    _add(
        api,
        case_id,
        destination_label="Greece",
        reason="Visiting family",
        departure_date="2024-07-01",
        return_date="2024-07-20",
    )
    _add(api, case_id, destination_label="France", date_confidence="ESTIMATED")
    _add(
        api,
        case_id,
        destination_label="Italy",
        departure_date="2019-05-01",
        return_date="2019-05-05",
    )
    removed = _add(api, case_id, destination_label="Portugal")
    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{removed['id']}")

    body = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records/export").json()
    assert body["scope"] == "WINDOW"
    assert body["period_text"] == (
        "Trips between 16 April 2022 and 15 April 2027: the five years up to the "
        "application date of 15 April 2027."
    )
    assert [(t["destination_label"], t["reason"]) for t in body["trips"]] == [
        ("France", None),
        ("Greece", "Visiting family"),
    ]
    assert body["trips"][0]["markers"] == [{"code": "ESTIMATED", "text": "Dates estimated"}]
    assert body["prepared_text"].startswith("Prepared from the applicant's own records on ")


@pytest.mark.integration
def test_a_case_with_no_application_date_lists_every_trip_and_says_why(api: Api) -> None:
    """The one case the period cannot apply to. Not a choice offered on the page: with no
    date there is no period, so the list is the whole history, labelled as such."""
    case_id = _case(api, with_date=False)
    _add(
        api,
        case_id,
        destination_label="Italy",
        departure_date="2019-05-01",
        return_date="2019-05-05",
        reason="Holiday",
    )
    body = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records/export").json()
    assert body["scope"] == "ALL"
    assert body["period_text"] is None
    assert [t["destination_label"] for t in body["trips"]] == ["Italy"]
    assert [c["code"] for c in body["cautions"]] == ["NO_APPLICATION_DATE"]


@pytest.mark.integration
def test_the_csv_is_an_attachment_nobody_caches(api: Api) -> None:
    case_id = _case(api)
    _add(api, case_id, reason="Holiday")
    resp = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"].startswith("attachment; filename=")
    assert resp.headers["cache-control"] == "no-store"
    rows = _rows(resp.content.decode("utf-8"))
    assert rows[1][:2] == ["Spain", "Holiday"]


@pytest.mark.integration
def test_another_user_cannot_export_the_trips(api: Api) -> None:
    case_id = _case(api)
    _add(api, case_id)
    assert api("user_b").get(f"/api/v1/cases/{case_id}/travel-records/export").status_code == 404
    assert (
        api("user_b").get(f"/api/v1/cases/{case_id}/travel-records/export.csv").status_code == 404
    )
