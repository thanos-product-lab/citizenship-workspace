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
    # The 439 result is retained but superseded — history inspectable, exactly one current.
    assert len(after["history"]) == 2
    currencies = [row["currency"] for row in after["history"]]
    assert currencies.count("CURRENT") == 1  # never two current for one requirement
    assert currencies.count("SUPERSEDED") == 1  # the 439 predecessor is retired, not orphaned


def test_the_canonical_case_shows_exactly_two_standing_issues(
    api: Api, db_session: Session
) -> None:
    """SYNTHETIC_DEMO_CASE §10's oracle, from M7 slice 4a.

    `NEAR_THRESHOLD` on the absence total, and one `MISSING_EVIDENCE` on trip 6 (Greece).
    The seed attaches a document to the other eleven trips, so the bare one is a
    deliberate hole in otherwise complete coverage rather than an artefact of an empty
    library — which is what the suppression gate would produce if coverage were simply
    absent.

    Two, not one: the M6 oracle was one standing issue, and this test exists so that
    number is stated somewhere a change has to walk past.
    """
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    queue = api("user_a").get(f"/api/v1/cases/{case_id}/issues").json()
    issues = [issue for group in queue["groups"] for issue in group["issues"]]

    by_type = sorted(issue["issue_type"] for issue in issues)
    assert by_type == ["MISSING_EVIDENCE", "NEAR_THRESHOLD"]

    missing = next(i for i in issues if i["issue_type"] == "MISSING_EVIDENCE")
    assert "Greece" in missing["title"], "the one trip the seed leaves without a document"
    assert missing["severity"] == "INFORMATION"
    assert missing["dismissibility"] == "DISMISSIBLE"


def test_editing_a_trip_does_not_disturb_which_trips_have_documents(
    api: Api, db_session: Session
) -> None:
    """The reason trip 6 was chosen for the coverage hole rather than trip 11.

    Editing trip 11's dates drives the stale-transition demo. Because an evidence link
    points at the travel *record* and not at a version (ADR-0021), that edit leaves every
    attachment where it was — so the `MISSING_EVIDENCE` item sits untouched beside four
    `STALE_ASSESSMENT` items that clear themselves, and the contrast the demo exists for
    stays legible.

    A version-scoped link would instead have detached trip 11's document on edit, opening
    a second coverage issue mid-demo for a document the user never touched.
    """
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    trips = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    trip_11 = next(t for t in trips if t["departure_date"] == "2026-05-04")
    assert trip_11["supporting_evidence_item_ids"], "trip 11 starts with a document"

    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{trip_11['id']}",
        json={
            "destination_label": "Italy",
            "departure_date": "2026-05-04",
            "return_date": "2026-05-11",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    after = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    edited = next(t for t in after if t["id"] == trip_11["id"])
    assert edited["supporting_evidence_item_ids"] == trip_11["supporting_evidence_item_ids"]

    queue = api("user_a").get(f"/api/v1/cases/{case_id}/issues").json()
    missing = [
        i
        for group in queue["groups"]
        for i in group["issues"]
        if i["issue_type"] == "MISSING_EVIDENCE"
    ]
    assert len(missing) == 1, "still only Greece"
