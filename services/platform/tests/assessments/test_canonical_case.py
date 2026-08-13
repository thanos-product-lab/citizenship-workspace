"""The canonical synthetic case as the integration oracle (M3B hard gate).

Every expected value here is a **literal transcribed by hand** from
`docs/product/SYNTHETIC_DEMO_CASE.md` — which derived them by hand from the rules spec —
never computed by the evaluator under test. That independence is the whole point: a test
that recomputed its expected value from the same code would prove nothing. The seed runs
through the real command path (`seed_demo_case`), so seed-vs-product drift is caught too.

M3B scope: the route, status, and residence requirements. `knowledge.*`, `referees.*`,
`character.review`, and `preparation.case_complete` need input models that arrive at M4,
so they read NOT_YET_ASSESSED here. `travel_consistency` is SUPPORTED because trip 11 is
EXACT at M3B; the INCONSISTENT conflict is M4 (see the doc's M3B/M4 staging note).
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.seed.demo_case import seed_demo_case

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _detail(api: Api, case_id: str, key: str) -> dict[str, Any]:
    body: dict[str, Any] = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/{key}").json()
    return body


def _conclusions(api: Api, case_id: str) -> dict[str, str]:
    rows = api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    return {row["requirement_key"]: row["conclusion"] for row in rows}


def test_canonical_case_produces_the_documented_oracle(api: Api, db_session: Session) -> None:
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    resp = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert resp.status_code == 200

    conclusions = _conclusions(api, case_id)
    # Conclusions — SYNTHETIC_DEMO_CASE.md §5 (M3B rows).
    assert conclusions["route.adult_applicant"] == "SUPPORTED"
    assert conclusions["route.supported_status"] == "SUPPORTED"
    assert conclusions["route.standard_section_6_1"] == "SUPPORTED"
    assert conclusions["status.holding_period"] == "SUPPORTED"
    assert conclusions["residence.qualifying_period"] == "SUPPORTED"
    assert conclusions["residence.physical_presence_start_date"] == "NOT_CURRENTLY_SATISFIED"
    assert conclusions["residence.total_absences"] == "NEAR_THRESHOLD"
    assert conclusions["residence.final_year_absences"] == "SUPPORTED"
    assert conclusions["residence.travel_consistency"] == "SUPPORTED"

    # The hand-derived numbers.
    total = _detail(api, case_id, "residence.total_absences")
    assert total["summary_parameters"]["days"] == 439  # §5 working: sum with no overlaps
    final_year = _detail(api, case_id, "residence.final_year_absences")
    assert final_year["summary_parameters"]["days"] == 17  # trips 11 (5) + 12 (12)

    presence = _detail(api, case_id, "residence.physical_presence_start_date")
    assert presence["summary_parameters"]["resolving_application_date"] == "2027-04-25"  # §8

    # Trip 1 straddles the presence anchor → a boundary note, but records stay consistent.
    consistency = _detail(api, case_id, "residence.travel_consistency")
    assert any(lim["code"] == "NEAR_STANDARD_THRESHOLD" for lim in consistency["limitations"])

    # Knowledge/referee/character/preparation inputs are M4 → not assessed here.
    assert conclusions["knowledge.life_in_uk"] == "NOT_YET_ASSESSED"
    assert conclusions["referees.second"] == "NOT_YET_ASSESSED"
    assert conclusions["preparation.case_complete"] == "NOT_YET_ASSESSED"


def test_canonical_stale_transition_moves_439_to_440(api: Api, db_session: Session) -> None:
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    before = _detail(api, case_id, "residence.total_absences")
    assert before["summary_parameters"]["days"] == 439
    assert before["currency"] == "CURRENT"

    # Resolve trip 11 to its booking value: return 10 May → 11 May (a direct edit stands in
    # for the M4 confirm-correction). Trip 11 departs 2026-05-04, unique in the fixture.
    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    trip11 = next(r for r in records if r["departure_date"] == "2026-05-04")
    edit = api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{trip11['id']}",
        json={
            "destination_label": "Italy",
            "departure_date": "2026-05-04",
            "return_date": "2026-05-11",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )
    assert edit.status_code == 200

    # The conclusion still stands, the currency has gone STALE (conclusion ⟂ currency).
    stale = _detail(api, case_id, "residence.total_absences")
    assert stale["conclusion"] == "NEAR_THRESHOLD"
    assert stale["currency"] == "STALE"
    assert stale["summary_parameters"]["days"] == 439  # last conclusion, unchanged until recalc

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    after = _detail(api, case_id, "residence.total_absences")
    assert after["summary_parameters"]["days"] == 440  # one extra absent day (10 May now counts)
    assert after["conclusion"] == "NEAR_THRESHOLD"  # 440 does not cross the 450 band boundary
    assert after["currency"] == "CURRENT"
    # The 439 result is retained, now superseded — history stays inspectable.
    assert len(after["history"]) == 2
