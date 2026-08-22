"""The residence timeline projection (Domain §44.3).

Expected values are transcribed from `SYNTHETIC_DEMO_CASE.md` §3/§4/§8 by hand, never
recomputed from the code under test — the per-trip counted days are the §4 table's own
"Absent days" column, which the doc derived from the rules spec.

The distinction this suite is really pinning: the timeline describes **inputs**, and the
Requirements destination describes **conclusions**. They can disagree, and when they do it
is because an assessment has not been rerun. A projection that quietly agreed by reading
the persisted results would hide exactly the state the user needs to see.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.seed.demo_case import DEMO_TRIPS, seed_demo_case

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

# SYNTHETIC_DEMO_CASE.md §4, "Absent days" — the count falling inside the qualifying
# window, in seed order. Trip 1 is the boundary case: 11 days abroad, 10 of them counted.
COUNTED_DAYS = (10, 40, 25, 66, 29, 39, 55, 51, 56, 51, 5, 12)


def _timeline(api: Api, case_id: str, user: str = "user_a") -> Any:
    return api(user).get(f"/api/v1/cases/{case_id}/timeline")


def _add_trip(api: Api, case_id: str, **overrides: Any) -> None:
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Trip",
            "departure_date": "2023-06-01",
            "return_date": "2023-07-02",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            **overrides,
        },
    )


def test_the_timeline_derives_the_windows_from_the_application_date(
    api: Api, db_session: Session
) -> None:
    """§3: the +1 day. Five years before 15 Apr 2027 is 15 Apr 2022, but the inclusive
    period *ending* on that date begins the 16th — which is the single most consequential
    day in the product, because it is the day presence is tested on."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    body = _timeline(api, case_id).json()

    assert body["application_date"] == "2027-04-15"
    assert body["qualifying_period_start"] == "2022-04-16"
    assert body["qualifying_period_end"] == "2027-04-15"
    assert body["final_year_start"] == "2026-04-16"
    assert body["final_year_end"] == "2027-04-15"
    assert body["presence_anchor"] == "2022-04-16"


def test_every_trip_reports_the_days_the_window_actually_counts(
    api: Api, db_session: Session
) -> None:
    """The §4 table, transcribed. `counted_days` is the figure a user cannot derive from
    the dates alone, and trip 1 is why: it is abroad 15-25 Apr 2022 (11 days) and
    contributes 10, because the window opens on the 16th (RULES_SPEC §5.3)."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    trips = _timeline(api, case_id).json()["trips"]

    assert [trip["counted_days"] for trip in trips] == list(COUNTED_DAYS)
    assert sum(COUNTED_DAYS) == 439  # the doc's headline total, arrived at independently

    first = trips[0]
    assert first["destination_label"] == "Spain"
    assert first["absent_days"] == 11, "the trip's own length"
    assert first["counted_days"] == 10, "what the window counts"
    assert first["covers_presence_anchor"] is True


def test_the_totals_match_the_documented_oracle(api: Api, db_session: Session) -> None:
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    totals = _timeline(api, case_id).json()["totals"]

    assert totals["qualifying_period_days"] == 439  # §5 working
    assert totals["final_year_days"] == 17  # trips 11 (5) + 12 (12)
    assert totals["trip_count"] == len(DEMO_TRIPS)
    assert totals["unconfirmed_trip_count"] == 0
    # Every record is CONFIRMED + EXACT at this milestone, so the two senses agree and the
    # §6.2 machinery has nothing to act on — the common case it exists to handle.
    assert totals["qualifying_period_days_including_unconfirmed"] == 439
    assert totals["final_year_days_including_unconfirmed"] == 17


def test_the_anchor_is_reported_as_absent_when_a_trip_covers_it(
    api: Api, db_session: Session
) -> None:
    """The fact the whole date-simulation interaction exists to move."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    body = _timeline(api, case_id).json()

    assert body["presence_anchor_is_absent"] is True
    covering = [trip for trip in body["trips"] if trip["covers_presence_anchor"]]
    assert [trip["destination_label"] for trip in covering] == ["Spain"]


def test_an_unconfirmed_trip_is_marked_untrusted_and_counted_separately(
    api: Api, db_session: Session
) -> None:
    """RULES_SPEC §6.1: only ACTIVE + CONFIRMED + EXACT enters a trusted total. The trip is
    still shown — hiding it would be its own kind of lie — but it is marked, and its days
    appear only in the including-unconfirmed figure."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    _add_trip(api, case_id, date_confidence="ESTIMATED", destination_label="Maybe")

    body = _timeline(api, case_id).json()
    uncertain = next(trip for trip in body["trips"] if trip["destination_label"] == "Maybe")
    assert uncertain["is_trusted"] is False
    assert uncertain["counted_days"] == 30

    totals = body["totals"]
    assert totals["qualifying_period_days"] == 439, "trusted total is unmoved"
    assert totals["qualifying_period_days_including_unconfirmed"] == 469
    assert totals["unconfirmed_trip_count"] == 1


def test_overlapping_trips_name_each_other_and_do_not_double_count(
    api: Api, db_session: Session
) -> None:
    """Totals are a union, so an overlap cannot inflate a figure (RULES_SPEC §5.2) — but it
    does mean one of the records is wrong, so each names the other."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    _add_trip(api, case_id, departure_date="2023-02-10", return_date="2023-02-20")

    body = _timeline(api, case_id).json()
    overlapping = [trip for trip in body["trips"] if trip["overlaps_with"]]
    assert len(overlapping) == 2
    assert {trip["destination_label"] for trip in overlapping} == {"France", "Trip"}
    for trip in overlapping:
        assert trip["travel_record_id"] not in trip["overlaps_with"]
    # France is 3 Feb - 1 Mar and already covered those days, so the union is unchanged.
    assert body["totals"]["qualifying_period_days"] == 439


def test_a_trip_outside_the_window_is_kept_and_marked(api: Api, db_session: Session) -> None:
    """RULES_SPEC §7.8: informational only, excluded from totals. Deleting it would be
    destroying the user's record; counting it would be wrong."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    _add_trip(
        api,
        case_id,
        departure_date="2015-01-01",
        return_date="2015-02-01",
        destination_label="Long ago",
    )

    body = _timeline(api, case_id).json()
    old = next(trip for trip in body["trips"] if trip["destination_label"] == "Long ago")
    assert old["is_outside_window"] is True
    assert old["counted_days"] == 0
    assert old["absent_days"] == 30, "the trip is still described accurately"
    assert body["totals"]["qualifying_period_days"] == 439


def test_the_timeline_says_when_the_conclusions_are_behind_the_records(
    api: Api, db_session: Session
) -> None:
    """The link between this projection and the Requirements destination.

    The figures here are computed from the records as they stand; the conclusions there
    were reached at a point in time. After an edit the two disagree, and a projection that
    did not say so would leave the user to discover it by comparing two screens."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _timeline(api, case_id).json()["assessment_is_stale"] is False

    _add_trip(api, case_id)

    body = _timeline(api, case_id).json()
    assert body["assessment_is_stale"] is True
    assert body["totals"]["qualifying_period_days"] == 469, "the records moved"


def test_a_case_with_no_application_date_has_no_timeline(api: Api) -> None:
    """Null, not an error: without a date there is no window and every counted figure is
    undefined, but the trips are real and listing them is the view's call to make."""
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "c"}).json()["id"])
    api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={
            "date_of_birth": "1990-05-01",
            "status_type": "ILR",
            "status_granted_on": "2019-01-01",
            "married_to_british_citizen": False,
            "may_already_be_british": False,
        },
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    response = _timeline(api, case_id)
    assert response.status_code == 200
    assert response.json() is None


def test_a_timeline_is_not_visible_to_another_user(api: Api, db_session: Session) -> None:
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    assert _timeline(api, case_id, user="user_b").status_code == 404
