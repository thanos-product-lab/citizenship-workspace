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


def _nested(row: dict[str, object], key: str) -> dict[str, object]:
    """A nested response object, narrowed. Response bodies are `dict[str, object]`, so
    reaching into `row["summary"]["text"]` is not type-safe without this."""
    value = row[key]
    assert isinstance(value, dict), f"expected {key} to be an object, got {value!r}"
    return value


def test_recalculate_persists_current_route_results(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")

    resp = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "TRUSTED"
    assert body["result_count"] == 9  # three route + status + five residence rules

    rows = _by_key(body["requirements"])
    assert len(rows) == 15  # the whole catalogue is projected, assessed or not
    for key in ROUTE_KEYS:
        assert rows[key]["conclusion"] == "SUPPORTED"
        assert rows[key]["currency"] == "CURRENT"
    # With no trips, the residence totals are zero → SUPPORTED and CURRENT.
    assert rows["residence.total_absences"]["conclusion"] == "SUPPORTED"
    assert rows["residence.total_absences"]["currency"] == "CURRENT"
    assert rows["status.holding_period"]["conclusion"] == "SUPPORTED"
    # A requirement whose evaluator does not exist yet is NOT_YET_ASSESSED, currency null.
    assert rows["knowledge.life_in_uk"]["conclusion"] == "NOT_YET_ASSESSED"
    assert rows["knowledge.life_in_uk"]["currency"] is None


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
    assert current == 9  # one CURRENT per assessed requirement (3 route + status + 5 residence)
    assert superseded == 9  # the first run's nine, now superseded


def test_requirements_are_not_visible_to_another_user(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert api("user_b").get(f"/api/v1/cases/{case_id}/requirements").status_code == 404
    assert api("user_b").post(f"/api/v1/cases/{case_id}/assessments/recalculate").status_code == 404


# --- derived case phase (Domain §7.5, ADR-0009) -----------------------------


def test_a_draft_case_reports_setting_up(api: Api) -> None:
    case_id = _draft_case(api, "user_a")
    body = api("user_a").get(f"/api/v1/cases/{case_id}").json()
    assert body["current_phase"] == "SETTING_UP"


def test_an_assessed_case_no_longer_reports_the_stored_setting_up(api: Api) -> None:
    """The regression this derivation exists for. `cases.current_phase` is written once at
    creation and never advanced, so before ADR-0009 a fully assessed case told the user it
    was still "Setting up". The phase must now come from the assessment state."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    body = api("user_a").get(f"/api/v1/cases/{case_id}").json()
    assert body["current_phase"] != "SETTING_UP"
    # Nine requirements assessed and clean (this case records no travel), six with no
    # result at all — so the honest phase is BUILDING_CASE, not "prepared".
    assert body["current_phase"] == "BUILDING_CASE"


def test_the_derived_phase_appears_in_the_case_list_too(api: Api) -> None:
    """The list endpoint derives in one batched query rather than per case, so it needs its
    own assertion — a projection that only fixed the detail endpoint would still lie here."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    rows = api("user_a").get("/api/v1/cases").json()
    listed = next(row for row in rows if row["id"] == case_id)
    assert listed["current_phase"] == "BUILDING_CASE"


def test_a_stale_result_alone_moves_the_phase_to_resolving_issues(api: Api) -> None:
    """Currency is enough (ADR-0001). Changing the application date restales the residence
    results; the phase must reflect that even though every conclusion still stands."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert api("user_a").get(f"/api/v1/cases/{case_id}").json()["current_phase"] == "BUILDING_CASE"

    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    changed = api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-05-20", "expected_revision": current["revision"]},
    )
    assert changed.status_code == 200, changed.text

    body = api("user_a").get(f"/api/v1/cases/{case_id}").json()
    assert body["current_phase"] == "RESOLVING_ISSUES"


# --- rendered summaries on the projections (M4 slice 1) ---------------------


def test_requirement_list_carries_code_parameters_and_rendered_text(api: Api) -> None:
    """All three travel together: the code and parameters stay machine-readable, and the
    text is rendered server-side from them so the wording is part of the contract."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    rows = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    total = rows["residence.total_absences"]
    summary = _nested(total, "summary")
    assert summary["code"] == total["summary_code"] == "TOTAL_ABSENCES_WITHIN_THRESHOLD"
    assert _nested(summary, "parameters")["threshold"] == 450
    text = summary["text"]
    assert isinstance(text, str) and "confirmed travel records" in text


def test_an_unassessed_requirement_has_no_summary_and_no_currency(api: Api) -> None:
    """The honest shape of "not looked at yet": NOT_YET_ASSESSED with a null currency and
    no summary at all. A currency of CURRENT here would claim the requirement had been
    assessed and found up to date."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    rows = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    referee = rows["referees.first"]
    assert referee["conclusion"] == "NOT_YET_ASSESSED"
    assert referee["currency"] is None
    assert referee["summary"] is None
    assert referee["stale"] is None


def test_a_current_result_carries_no_stale_block(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    rows = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    assert rows["residence.total_absences"]["currency"] == "CURRENT"
    assert rows["residence.total_absences"]["stale"] is None


def test_a_stale_result_keeps_its_conclusion_and_explains_its_currency(api: Api) -> None:
    """The ADR-0001 shape the UI has to render: the conclusion is untouched, the currency
    says STALE, and the stale block explains why — three separate signals, never merged."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    conclusion_before = before["residence.total_absences"]["conclusion"]

    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-05-20", "expected_revision": current["revision"]},
    )

    row = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())[
        "residence.total_absences"
    ]
    assert row["conclusion"] == conclusion_before  # the conclusion is never rewritten
    assert row["currency"] == "STALE"
    stale = _nested(row, "stale")
    assert stale["reason_code"] == "APPLICATION_DATE_CHANGED"
    assert stale["reason"] == "Your proposed application date changed after this was worked out."
    assert stale["marked_stale_at"] is not None
    # The summary still describes the conclusion that was reached; staleness is separate.
    assert _nested(row, "summary")["text"]


def test_requirement_detail_renders_the_same_summary_as_the_list(api: Api) -> None:
    """Two projections of one result must not disagree about what it says."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    listed = _by_key(api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json())
    detail = (
        api("user_a").get(f"/api/v1/cases/{case_id}/requirements/residence.total_absences").json()
    )
    assert detail["summary"] == listed["residence.total_absences"]["summary"]


def test_every_assessed_requirement_renders_some_text(api: Api) -> None:
    """A null `text` on a result that has a summary code means a missing template shipped."""
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    for row in api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json():
        if row["summary"] is None:
            continue
        summary = _nested(row, "summary")
        assert summary["text"], f"{row['requirement_key']} has no rendered text"
