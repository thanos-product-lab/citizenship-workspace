"""The case overview projection over the real API (Domain §44.1).

The assertions worth having are about what the overview must not claim: no readiness
score, no group reading as complete while it holds unassessed requirements, no group
reading as current while a member is stale, and no zero for a thing nothing has counted.
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


def _active_case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    return case_id


def _assessed_case(api: Api, user: str, date: str = "2027-04-15") -> str:
    case_id = _active_case(api, user)
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select", json={"application_date": date}
    )
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    return case_id


Json = dict[str, Any]


def _overview(api: Api, user: str, case_id: str) -> Json:
    resp = api(user).get(f"/api/v1/cases/{case_id}/overview")
    assert resp.status_code == 200, resp.text
    body: Json = resp.json()
    return body


def _group(overview: Json, key: str) -> Json:
    groups: list[Json] = overview["groups"]
    return next(g for g in groups if g["group_key"] == key)


def test_overview_reports_the_derived_phase_not_the_stored_column(api: Api) -> None:
    case_id = _assessed_case(api, "user_a")
    assert _overview(api, "user_a", case_id)["current_phase"] != "SETTING_UP"


def test_groups_cover_every_catalogued_requirement_exactly_once(api: Api) -> None:
    overview = _overview(api, "user_a", _assessed_case(api, "user_a"))
    assert sum(g["total"] for g in overview["groups"]) == overview["total_requirements"] == 15
    keys = [r["requirement_key"] for g in overview["groups"] for r in g["requirements"]]
    assert len(keys) == len(set(keys)) == 15


def test_an_unassessed_group_is_not_fully_concluded_and_has_no_currency(api: Api) -> None:
    """Referees has no evaluator. It must not read as complete, and must not report a
    currency — 'current' would claim it had been assessed and found up to date."""
    referees = _group(_overview(api, "user_a", _assessed_case(api, "user_a")), "REFEREES")
    assert referees["not_yet_assessed"] == 2
    assert referees["conclusion_counts"] == {}
    assert referees["is_fully_concluded"] is False
    assert referees["currency"] is None


def test_an_assessed_group_reports_counts_by_named_state(api: Api) -> None:
    residence = _group(_overview(api, "user_a", _assessed_case(api, "user_a")), "RESIDENCE")
    assert residence["total"] == 5
    assert residence["is_fully_concluded"] is True
    assert residence["currency"] == "CURRENT"
    assert sum(residence["conclusion_counts"].values()) == 5


def test_a_stale_member_makes_its_group_stale_but_not_the_others(api: Api) -> None:
    """ADR-0010 over the wire. Changing the application date restales the residence group;
    knowledge and referees are untouched."""
    case_id = _assessed_case(api, "user_a")
    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-05-20", "expected_revision": current["revision"]},
    )

    overview = _overview(api, "user_a", case_id)
    residence = _group(overview, "RESIDENCE")
    assert residence["currency"] == "STALE"
    assert residence["stale"] == 5
    # The conclusions are preserved — staleness never rewrites what was concluded.
    assert sum(residence["conclusion_counts"].values()) == 5
    assert _group(overview, "REFEREES")["currency"] is None
    assert overview["stale"] == 5


def test_the_overview_reports_no_readiness_score(api: Api) -> None:
    """CLAUDE.md §2.6. The payload carries counts of named states and the number of things
    not yet assessed — never a fraction, percentage, or completion measure."""
    overview = _overview(api, "user_a", _assessed_case(api, "user_a"))
    forbidden = {"percent", "percentage", "score", "readiness", "progress", "completion"}
    assert not (forbidden & set(overview)), overview.keys()
    for group in overview["groups"]:
        assert not (forbidden & set(group))


def test_issue_count_and_evidence_coverage_are_absent_not_zero(api: Api) -> None:
    """Domain §44.1 lists both, but issues are M6 and evidence is M5. A zero would say the
    system looked and found none — a stronger claim than the product can make."""
    overview = _overview(api, "user_a", _assessed_case(api, "user_a"))
    assert "open_issue_count" not in overview
    assert "evidence_coverage" not in overview


def test_priority_actions_are_capped_at_three_and_carry_rendered_text(api: Api) -> None:
    case_id = _assessed_case(api, "user_a")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Spain",
            "departure_date": "2022-04-14",
            "return_date": "2022-04-26",
        },
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    overview = _overview(api, "user_a", case_id)
    assert len(overview["priority_actions"]) <= 3
    action = overview["priority_actions"][0]
    assert action["requirement_key"] == "residence.physical_presence_start_date"
    assert action["blocking"] is True
    assert action["text"] and "25 April 2027" in action["text"]
    assert overview["priority_actions_hidden"] == 0


def test_a_case_with_no_application_date_still_renders(api: Api) -> None:
    """The overview must not require a date: a freshly activated case has none, and
    raising here would make the landing screen unreachable."""
    overview = _overview(api, "user_a", _active_case(api, "user_a"))
    assert overview["application_date"] is None
    assert overview["not_yet_assessed"] == 15
    assert overview["priority_actions"] == []
    assert overview["last_assessed_at"] is None


def test_the_overview_is_scoped_to_its_owner(api: Api) -> None:
    case_id = _assessed_case(api, "user_a")
    assert api("user_b").get(f"/api/v1/cases/{case_id}/overview").status_code == 404


def test_the_canonical_case_shape(api: Api) -> None:
    """The M3B oracle as an overview: nine assessed, six unassessed, all current."""
    overview = _overview(api, "user_a", _assessed_case(api, "user_a"))
    assert overview["total_requirements"] == 15
    assert overview["not_yet_assessed"] == 6
    assert overview["stale"] == 0
    assert overview["application_date"] == "2027-04-15"
