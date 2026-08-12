"""Slice-1 assessment write path: run → results → input links, and the read projections.

Proves the infrastructure end-to-end on the already-tested route.* evaluators: a trusted
run persists immutable, current results with exact provenance; re-running supersedes the
prior result and never leaves two current; and the requirement projections read conclusion
and currency as separate dimensions. The residence/status/knowledge rules join in later
slices; here every non-route requirement is honestly NOT_YET_ASSESSED.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentResult
from app.requirements.domain import Currency

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}
ROUTE_KEYS = {"route.adult_applicant", "route.supported_status", "route.standard_section_6_1"}


def _draft_case(api: Api, user: str) -> str:
    return str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])


def _active_case(api: Api, user: str) -> str:
    case_id = _draft_case(api, user)
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    return case_id


def _case_with_date(api: Api, user: str, application_date: str = "2027-04-15") -> str:
    case_id = _active_case(api, user)
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": application_date},
    )
    return case_id


def _by_key(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["requirement_key"]): row for row in rows}


def test_recalculate_persists_current_route_results(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")

    resp = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "TRUSTED"
    assert body["result_count"] == 7  # three route + four residence rules

    rows = _by_key(body["requirements"])
    assert len(rows) == 15  # the whole catalogue is projected, assessed or not
    for key in ROUTE_KEYS:
        assert rows[key]["conclusion"] == "SUPPORTED"
        assert rows[key]["currency"] == "CURRENT"
    # With no trips, the residence totals are zero → SUPPORTED and CURRENT.
    assert rows["residence.total_absences"]["conclusion"] == "SUPPORTED"
    assert rows["residence.total_absences"]["currency"] == "CURRENT"
    # A requirement whose evaluator does not exist yet is NOT_YET_ASSESSED, currency null.
    assert rows["status.holding_period"]["conclusion"] == "NOT_YET_ASSESSED"
    assert rows["status.holding_period"]["currency"] is None


def test_requirements_are_not_yet_assessed_before_a_run(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    rows = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    assert len(rows) == 15
    assert all(
        r["conclusion"] == "NOT_YET_ASSESSED" and r["currency"] is None for r in rows.values()
    )


def test_route_conclusions_come_from_results_not_the_confirm_event(api: Api) -> None:
    """Single source of truth (ADR-0007): confirming the route emits RouteSupportEvaluated
    and sets the case's support_status, but that does NOT populate the requirement
    conclusions. The route rows stay NOT_YET_ASSESSED until a trusted run writes results;
    only then do the conclusions appear — proving the read model reads AssessmentResult
    alone, never the confirm event."""
    case_id = _case_with_date(api, "user_a")

    before = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    assert all(before[key]["conclusion"] == "NOT_YET_ASSESSED" for key in ROUTE_KEYS)

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    after = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    assert all(after[key]["conclusion"] == "SUPPORTED" for key in ROUTE_KEYS)


def test_recalculate_needs_a_selected_application_date(api: Api) -> None:
    case_id = _active_case(api, "user_a")  # active, but no date selected
    resp = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert resp.status_code == 409
    assert resp.json()["code"] == "CASE_NOT_ASSESSABLE"


def test_recalculate_needs_an_active_case(api: Api) -> None:
    case_id = _draft_case(api, "user_a")  # still onboarding
    resp = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert resp.status_code == 409
    assert resp.json()["code"] == "CASE_NOT_ACTIVE"


def test_detail_exposes_conclusion_currency_and_provenance(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    detail = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/route.adult_applicant").json()
    assert detail["conclusion"] == "SUPPORTED"
    assert detail["currency"] == "CURRENT"
    assert detail["guidance"]  # a rule cites at least one guidance source
    assert len(detail["history"]) == 1
    # Adult reads the route profile (DOB) and the application date — two exact links.
    kinds = sorted(link["input_kind"] for link in detail["input_links"])
    assert kinds == ["APPLICATION_DATE_VERSION", "ROUTE_PROFILE_VERSION"]


def test_unknown_requirement_key_is_404(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    resp = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/not.a.requirement")
    assert resp.status_code == 404


def test_recalculation_supersedes_and_keeps_one_current(api: Api, db_session: Session) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    # Two runs, so two adult results exist; exactly one is CURRENT, the other SUPERSEDED.
    detail = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/route.adult_applicant").json()
    assert len(detail["history"]) == 2
    assert detail["currency"] == "CURRENT"

    current = db_session.scalar(
        select(func.count())
        .select_from(AssessmentResult)
        .where(AssessmentResult.currency == Currency.CURRENT.value)
    )
    superseded = db_session.scalar(
        select(func.count())
        .select_from(AssessmentResult)
        .where(AssessmentResult.currency == Currency.SUPERSEDED.value)
    )
    assert current == 7  # one CURRENT per assessed requirement (3 route + 4 residence)
    assert superseded == 7  # the first run's seven, now superseded


def test_requirements_are_not_visible_to_another_user(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert api("user_b").get(f"/api/v1/cases/{case_id}/requirements").status_code == 404
    assert api("user_b").post(f"/api/v1/cases/{case_id}/assessments/recalculate").status_code == 404
