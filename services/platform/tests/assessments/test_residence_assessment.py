"""Residence assessment through the real command path: travel records → recalculate →
persisted residence results with structured breakdowns, limitations, next actions, and
exact travel-record provenance.

The evaluator maths is proved in tests/rules; here we prove the *wiring* — the §6.1 trust
gate applied to real records, the resolving date surfaced on failure, and one
ALL_ACTIVE_TRAVEL_RECORDS dependency resolving to a link per active record.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


def _case_with_date(api: Api, user: str, application_date: str = "2027-04-15") -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": application_date},
    )
    return case_id


def _add_trip(
    api: Api,
    user: str,
    case_id: str,
    *,
    departure: str,
    return_: str,
    confidence: str = "EXACT",
    review: str = "CONFIRMED",
    label: str = "Trip",
) -> None:
    api(user).post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": label,
            "departure_date": departure,
            "return_date": return_,
            "date_confidence": confidence,
            "review_state": review,
        },
    )


def _detail(api: Api, user: str, case_id: str, key: str) -> dict[str, Any]:
    body: dict[str, Any] = api(user).get(f"/api/v1/cases/{case_id}/requirements/{key}").json()
    return body


def test_trusted_trip_drives_the_absence_total_with_provenance(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    # A trusted 30-day trip well inside the window (not covering the anchor).
    _add_trip(api, "user_a", case_id, departure="2023-06-01", return_="2023-07-02")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    total = _detail(api, "user_a", case_id, "residence.total_absences")
    assert total["conclusion"] == "SUPPORTED"
    assert total["summary_parameters"]["days"] == 30
    # One application-date link plus one travel-record link (the ALL_ACTIVE dependency).
    kinds = sorted(item["input_kind"] for item in total["facts_used"] + total["travel_inputs"])
    assert kinds == ["APPLICATION_DATE_VERSION", "TRAVEL_RECORD_VERSION"]

    qualifying = _detail(api, "user_a", case_id, "residence.qualifying_period")
    assert qualifying["calculation_breakdown"]["qualifying_period_start"] == "2022-04-16"


def test_trip_over_the_anchor_fails_presence_and_offers_the_resolving_date(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    _add_trip(api, "user_a", case_id, departure="2022-04-14", return_="2022-04-26", label="Spain")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    presence = _detail(api, "user_a", case_id, "residence.physical_presence_start_date")
    assert presence["conclusion"] == "NOT_CURRENTLY_SATISFIED"
    assert presence["summary_parameters"]["resolving_application_date"] == "2027-04-25"
    assert presence["next_actions"][0]["code"] == "SELECT_APPLICATION_DATE"


def test_unconfirmed_trip_is_excluded_from_the_trusted_total(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    # One trusted trip (20 days) and one ESTIMATED trip (40 days): the trusted total counts
    # only the confirmed-exact one; the provisional total sees both (§6.1 gate).
    _add_trip(api, "user_a", case_id, departure="2023-01-01", return_="2023-01-22")
    _add_trip(
        api, "user_a", case_id, departure="2024-01-01", return_="2024-02-11", confidence="ESTIMATED"
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    total = _detail(api, "user_a", case_id, "residence.total_absences")
    assert total["summary_parameters"]["days"] == 20  # trusted only
    assert total["summary_parameters"]["provisional_days"] == 60  # both
    # Two active records → two travel links plus the application-date link.
    assert len(total["travel_inputs"]) == 2
    # And the screen can tell them apart: only the confirmed-exact record counted toward
    # the trusted figure, so a reader cannot mistake two rows for two confirmed inputs.
    assert sorted(item["counts_as_confirmed"] for item in total["travel_inputs"]) == [False, True]


def test_conflicting_trip_makes_travel_consistency_inconsistent(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    _add_trip(
        api,
        "user_a",
        case_id,
        departure="2023-01-01",
        return_="2023-01-22",
        confidence="CONFLICTING",
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    consistency = _detail(api, "user_a", case_id, "residence.travel_consistency")
    assert consistency["conclusion"] == "INCONSISTENT"
    assert consistency["summary_code"] == "TRAVEL_RECORDS_CONFLICT"

    # status.holding_period is now wired and reads SUPPORTED for a long-held ILR.
    status = _detail(api, "user_a", case_id, "status.holding_period")
    assert status["conclusion"] == "SUPPORTED"
