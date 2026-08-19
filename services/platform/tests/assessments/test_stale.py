"""Selective stale propagation (Domain §41): an input change marks the results whose rules
declare a dependency on it STALE in the same transaction; recalculation supersedes them and
writes new current results; a failed recalculation promotes nothing.

This is the conclusion-vs-currency separation made concrete (ADR-0001): a result can be
SUPPORTED and STALE at once, and its conclusion is never edited in place.

The counts here are deliberately literal (four stale after a travel change, eight after a
date change) rather than derived, so a change to the dependency declarations breaks a test
that names the number a human checked. `test_selective_invalidation.py` owns the derived
version and the reasoning behind the numbers; ADR-0014 owns the why.
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
RESIDENCE_KEYS = {
    "residence.qualifying_period",
    "residence.physical_presence_start_date",
    "residence.total_absences",
    "residence.final_year_absences",
    "residence.travel_consistency",
}
# The four residence rules that declare a TRAVEL_RECORD dependency. `qualifying_period` reads
# only the application date, so a travel change must leave it CURRENT — the over-invalidation
# half of ADR-0008, closed by ADR-0014.
TRAVEL_DEPENDENT_KEYS = RESIDENCE_KEYS - {"residence.qualifying_period"}
# A travel change stales 4; the other 5 results (3 route + status + qualifying_period) stand.
TRAVEL_STALE_COUNT = 4
UNAFFECTED_BY_TRAVEL_COUNT = 5


def _case_with_date(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    return case_id


def _add_trip(api: Api, user: str, case_id: str, dep: str, ret: str) -> str:
    return str(
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/travel-records",
            json={
                "destination_label": "Trip",
                "departure_date": dep,
                "return_date": ret,
                "date_confidence": "EXACT",
                "review_state": "CONFIRMED",
            },
        )
        .json()["id"]
    )


def _by_key(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["requirement_key"]): row for row in rows}


def _requirements(api: Api, user: str, case_id: str) -> dict[str, dict[str, object]]:
    return _by_key(api(user).get(f"/api/v1/cases/{case_id}/requirements").json())


def test_travel_change_marks_residence_results_stale(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    rows = _requirements(api, "user_a", case_id)
    # The travel-dependent results are STALE, but their conclusion still stands, unedited
    # (conclusion ⟂ currency).
    for key in TRAVEL_DEPENDENT_KEYS:
        assert rows[key]["currency"] == "STALE", key
        assert rows[key]["conclusion"] != "NOT_YET_ASSESSED"
    # `qualifying_period` derives from the application date alone. Under blunt invalidation it
    # was staled here too; selective invalidation leaves it alone.
    assert rows["residence.qualifying_period"]["currency"] == "CURRENT"
    # Nothing outside residence declares a travel dependency.
    assert rows["route.supported_status"]["currency"] == "CURRENT"
    assert rows["status.holding_period"]["currency"] == "CURRENT"


def test_recalculation_supersedes_stale_and_restores_current(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")  # → travel-dependent STALE
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")  # → refresh

    rows = _requirements(api, "user_a", case_id)
    for key in RESIDENCE_KEYS:
        assert rows[key]["currency"] == "CURRENT", key

    # The stale total-absences result is retained as history, now SUPERSEDED.
    total = (
        api("user_a").get(f"/api/v1/cases/{case_id}/requirements/residence.total_absences").json()
    )
    assert len(total["history"]) == 2
    assert total["conclusion"] == "SUPPORTED"


def test_no_current_result_is_ever_reported_stale_and_current(
    api: Api, db_session: Session
) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    # After the change: the four travel-dependent results STALE, none of them also CURRENT.
    stale = db_session.scalar(
        select(func.count())
        .select_from(AssessmentResult)
        .where(AssessmentResult.currency == Currency.STALE.value)
    )
    assert stale == TRAVEL_STALE_COUNT


def test_failed_recalculation_promotes_nothing(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")  # residence → STALE

    # Force the recalculation to fail before it persists anything.
    import app.assessments.service as service

    def _boom(_inputs: object) -> list[object]:
        raise RuntimeError("evaluator failed")

    monkeypatch.setattr(service, "evaluate_residence_requirements", _boom)
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    # §41.4: the old results stay STALE, nothing is superseded, nothing new becomes current.
    def _count(currency: Currency) -> int | None:
        return db_session.scalar(
            select(func.count())
            .select_from(AssessmentResult)
            .where(AssessmentResult.currency == currency.value)
        )

    assert _count(Currency.STALE) == TRAVEL_STALE_COUNT  # still stale
    # route (3) + status (1) + qualifying_period, none of which reads a travel record.
    assert _count(Currency.CURRENT) == UNAFFECTED_BY_TRAVEL_COUNT
    assert _count(Currency.SUPERSEDED) == 0  # the failed run superseded nothing


def test_failure_midway_through_persistence_rolls_back_fully(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Guards invariant #4 across a *partial* failure: if the recalc dies after superseding some
    # results but before finishing, the whole run rolls back — no two-current, nothing orphaned.
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")  # residence → STALE

    import app.assessments.service as service

    real_persist = service._persist_result
    calls = {"n": 0}

    def flaky_persist(*args: object, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] >= 3:  # let two results supersede + insert, then blow up mid-loop
            raise RuntimeError("persistence failed mid-run")
        real_persist(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service, "_persist_result", flaky_persist)
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    # In production the failed request's session closes uncommitted, discarding the mid-loop
    # supersede/insert writes; the shared test session models that with an explicit rollback.
    db_session.rollback()

    def _count(currency: Currency) -> int | None:
        return db_session.scalar(
            select(func.count())
            .select_from(AssessmentResult)
            .where(AssessmentResult.currency == currency.value)
        )

    # The partial supersede/insert work rolled back: back to 4 STALE + 5 CURRENT, none
    # superseded.
    assert _count(Currency.STALE) == TRAVEL_STALE_COUNT
    assert _count(Currency.CURRENT) == UNAFFECTED_BY_TRAVEL_COUNT
    assert _count(Currency.SUPERSEDED) == 0


def test_selecting_a_new_date_marks_residence_stale(api: Api) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-05-01"},
    )

    rows = _requirements(api, "user_a", case_id)
    assert rows["residence.qualifying_period"]["currency"] == "STALE"

    # The date reaches past residence. Under blunt invalidation these three read CURRENT while
    # the date beneath them had moved — ADR-0008's documented under-invalidation window, and
    # the reason M6 was not optional. `route.standard_section_6_1` declares no date dependency
    # at all; it is stale only because it composes `route.adult_applicant`'s conclusion (§25.4).
    assert rows["status.holding_period"]["currency"] == "STALE"
    assert rows["route.adult_applicant"]["currency"] == "STALE"
    assert rows["route.standard_section_6_1"]["currency"] == "STALE"

    # `route.supported_status` reads the status type, not the date, so it stands.
    assert rows["route.supported_status"]["currency"] == "CURRENT"

    stale = {key for key, row in rows.items() if row["currency"] == "STALE"}
    assert len(stale) == 8, sorted(stale)
