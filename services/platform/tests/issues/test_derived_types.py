"""The issue types derived from assessment output (Domain §36.2), end to end.

`test_issue_lifecycle.py` proves the lifecycle on one type. This file proves each type's
own rule: what raises it, what severity it carries, whether it can be set aside, and that
it clears when its cause does.

The dismissal path is exercised here for the first time. Until this slice every derived
issue was NOT_DISMISSIBLE, so the endpoint and the reconciler's handling of a dismissed row
were guarded only by unit-level tests.
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
# Qualifying window for this date is 2022-04-16 → 2027-04-15.
APPLICATION_DATE = "2027-04-15"


def _case(api: Api, user: str = "user_a") -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": APPLICATION_DATE},
    )
    return case_id


def _trip(
    api: Api,
    case_id: str,
    dep: str,
    ret: str,
    *,
    label: str = "Spain",
    confidence: str = "EXACT",
    review: str = "CONFIRMED",
    user: str = "user_a",
) -> str:
    return str(
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/travel-records",
            json={
                "destination_label": label,
                "departure_date": dep,
                "return_date": ret,
                "date_confidence": confidence,
                "review_state": review,
            },
        )
        .json()["id"]
    )


def _recalc(api: Api, case_id: str, user: str = "user_a") -> None:
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")


def _queue(api: Api, case_id: str, user: str = "user_a") -> dict[str, Any]:
    payload: dict[str, Any] = api(user).get(f"/api/v1/cases/{case_id}/issues").json()
    return payload


def _open(queue: dict[str, Any]) -> list[dict[str, Any]]:
    return [issue for group in queue["groups"] for issue in group["issues"]]


def _of_type(queue: dict[str, Any], issue_type: str) -> list[dict[str, Any]]:
    return [i for i in _open(queue) if i["issue_type"] == issue_type]


# --- NEAR_THRESHOLD ----------------------------------------------------------


def test_a_near_threshold_conclusion_raises_a_review_issue(api: Api) -> None:
    case_id = _case(api)
    # 440 days across the window: inside the near-threshold band below 450.
    _trip(api, case_id, "2023-01-01", "2024-03-15")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "NEAR_THRESHOLD")
    assert [i["affected_object_id"] for i in issues] == ["residence.total_absences"]
    assert issues[0]["severity"] == "REVIEW_REQUIRED"
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "close to its threshold" in issues[0]["title"]


def test_the_near_threshold_issue_never_states_the_gap_as_headroom(api: Api) -> None:
    """The copy rule that governs the summary governs the queue too: "10 days remaining"
    is advice, and invites reading NEAR_THRESHOLD as a pass with room to spare."""
    case_id = _case(api)
    _trip(api, case_id, "2023-01-01", "2024-03-15")
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "NEAR_THRESHOLD")[0]
    text = f"{issue['title']} {issue['body']} {issue['impact']}".lower()
    assert "remaining" not in text
    assert "left" not in text


def test_the_near_threshold_issue_clears_when_the_margin_widens(api: Api) -> None:
    case_id = _case(api)
    trip = _trip(api, case_id, "2023-01-01", "2024-03-15")
    _recalc(api, case_id)
    assert _of_type(_queue(api, case_id), "NEAR_THRESHOLD")

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{trip}",
        params={"expected_revision": record["revision"]},
    )
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "NEAR_THRESHOLD") == []


# --- UNSUPPORTED_COMPLEXITY --------------------------------------------------


def test_an_absence_total_the_prototype_will_not_assess_raises_a_blocking_issue(
    api: Api,
) -> None:
    """UI/UX §10.2. Stopping is a successful outcome (CLAUDE.md §2.7), so it is surfaced
    rather than buried in a requirement nobody opens."""
    case_id = _case(api)
    _trip(api, case_id, "2023-01-01", "2025-01-01")  # far past every band
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "UNSUPPORTED_COMPLEXITY")
    assert issues, _queue(api, case_id)
    assert issues[0]["severity"] == "BLOCKING"
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "paused" in (issues[0]["body"] or "")
    # And it does not also raise a near-threshold item for the same requirement.
    affected = {i["affected_object_id"] for i in _of_type(_queue(api, case_id), "NEAR_THRESHOLD")}
    assert "residence.total_absences" not in affected


def test_a_blocking_issue_cannot_be_dismissed(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-01-01", "2025-01-01")
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "UNSUPPORTED_COMPLEXITY")[0]
    assert api("user_a").post(
        f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss"
    ).status_code == 409


# --- OVERLAPPING_TRAVEL ------------------------------------------------------


def test_overlapping_trips_raise_one_issue_per_record(api: Api) -> None:
    """One per record rather than one per pair: a pair has no single affected object to
    name (§36.1), and the user fixes the overlap by editing one of the two records."""
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Spain")
    _trip(api, case_id, "2023-06-15", "2023-07-20", label="Portugal")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL")
    assert len(issues) == 2
    assert {i["severity"] for i in issues} == {"REVIEW_REQUIRED"}
    assert {i["affected_object_type"] for i in issues} == {"TravelRecord"}
    assert "Spain" in " ".join(i["title"] for i in issues)


def test_the_overlap_issue_clears_when_the_records_stop_overlapping(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Spain")
    _trip(api, case_id, "2023-06-15", "2023-07-20", label="Portugal")
    _recalc(api, case_id)
    assert len(_of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL")) == 2

    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    second = next(r for r in records if r["destination_label"] == "Portugal")
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{second['id']}",
        json={
            "destination_label": "Portugal",
            "departure_date": "2023-08-01",
            "return_date": "2023-08-20",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": second["revision"],
        },
    )
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL") == []


# --- UNCERTAIN_TRAVEL_DATE ---------------------------------------------------


def test_an_uncertain_date_inside_the_window_needs_an_action_and_cannot_be_dismissed(
    api: Api,
) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(issues) == 1
    assert issues[0]["severity"] == "ACTION_REQUIRED"
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "Confirm the dates" in issues[0]["title"]


def test_an_uncertain_date_outside_the_window_is_information_the_user_may_set_aside(
    api: Api,
) -> None:
    """The window judgement is the evaluator's, read from its limitation — this module
    never recomputes it (RULES_SPEC §7.8)."""
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(issues) == 1
    assert issues[0]["severity"] == "INFORMATION"
    assert issues[0]["dismissibility"] == "DISMISSIBLE"
    assert issues[0]["action_group"] == "FOR_YOUR_AWARENESS"


def test_an_uncertain_trip_keeps_its_issue_when_edited_but_still_uncertain(api: Api) -> None:
    """Identity is the record, not the version. Editing a trip mints a new version; if the
    issue were keyed on that, correcting a date without resolving the uncertainty would
    close one issue and open another, which reads as progress where there is none."""
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")
    _recalc(api, case_id)
    before = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Greece",
            "departure_date": "2023-06-02",
            "return_date": "2023-07-01",
            "date_confidence": "ESTIMATED",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)

    after = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    assert after["id"] == before["id"]
    assert after["reopened_at"] is None, "the issue should never have closed"


def test_confirming_the_dates_resolves_the_issue(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")
    _recalc(api, case_id)
    assert _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Greece",
            "departure_date": "2023-06-01",
            "return_date": "2023-07-01",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE") == []


# --- dismissal, end to end ---------------------------------------------------


def test_dismissing_hides_an_issue_without_deleting_it(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]

    response = api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")
    assert response.status_code == 200
    assert response.json()["status"] == "DISMISSED"

    queue = _queue(api, case_id)
    assert _of_type(queue, "UNCERTAIN_TRAVEL_DATE") == []
    dismissed = [i for i in queue["history"] if i["id"] == issue["id"]]
    assert len(dismissed) == 1
    assert dismissed[0]["status"] == "DISMISSED"
    assert [r["resolution_type"] for r in dismissed[0]["resolutions"]] == ["USER_DISMISSED"]


def test_a_dismissed_issue_stays_dismissed_while_its_cause_persists(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")

    # Another write reconciles. The cause is still there and the user has decided about it.
    _trip(api, case_id, "2024-02-01", "2024-03-01", label="Italy")
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE") == []
    assert _queue(api, case_id)["open_count"] == 0


def test_a_dismissed_issue_reopens_when_its_cause_goes_and_returns(api: Api) -> None:
    """Dismissal is a judgement about this episode, not a standing waiver on the cause.
    Now reachable through the API, where before it could only be driven directly."""
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")

    # Cause gone: the dismissal is spent and the issue leaves the live set.
    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Japan",
            "departure_date": "2021-01-10",
            "return_date": "2021-02-10",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)
    settled = [i for i in _queue(api, case_id)["history"] if i["id"] == issue["id"]]
    assert settled and settled[0]["status"] == "RESOLVED"

    # Cause returns: a new episode on the same row, not silence.
    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Japan",
            "departure_date": "2021-01-10",
            "return_date": "2021-02-10",
            "date_confidence": "ESTIMATED",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)

    reopened = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(reopened) == 1
    assert reopened[0]["id"] == issue["id"]
    assert reopened[0]["has_recurred"] is True
    assert [r["resolution_type"] for r in reopened[0]["resolutions"]] == [
        "SYSTEM_AUTO_RESOLVED",
        "USER_DISMISSED",
    ]
