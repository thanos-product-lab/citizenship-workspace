"""Invalidation completeness, checked against behaviour rather than against declarations.

Every other invalidation test trusts the dependency rows: it asks whether the resolver agrees
with what the rules *say* they read. This one trusts nothing. It recalculates, changes an
input, recalculates again, and diffs what the rules actually produced:

    every requirement whose output moved must have been staled

An evaluator that quietly reads an input it neither declares nor links passes the provenance
tests and the differential tests — both read the same declarations it is lying about — and is
caught only here, by its output changing while its currency did not. That is the failure mode
ADR-0008 shipped with and this file exists to make impossible to reintroduce silently.

The assertion is a subset, not an equality: over-firing is allowed and expected. Staling
`residence.qualifying_period` after a date move that leaves its window text identical is
correct behaviour, not a defect.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink, AssessmentResult
from app.requirements.domain import Currency
from app.requirements.models import RequirementDefinition

pytestmark = [pytest.mark.integration, pytest.mark.property]

Api = Callable[[str], TestClient]

# Each example builds its own case and filters every query by that case id, so reusing the
# function-scoped session across examples is safe — the health check that forbids it is
# guarding against shared *state*, and there is none here. Examples are few and each runs two
# full recalculations, so the deadline is off rather than tuned.
_PROPERTY = settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}

# A trip that straddles the qualifying-window boundary for the base date, and two that sit
# well inside it — boundary-straddling records are where an undeclared read is most likely
# to matter, because that is where a small date move changes which days count.
BASE_APPLICATION_DATE = date(2027, 4, 15)
SEED_TRIPS = (
    ("2022-04-10", "2022-04-24"),
    ("2024-02-01", "2024-03-01"),
    ("2026-05-04", "2026-05-10"),
)


def _case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": BASE_APPLICATION_DATE.isoformat()},
    )
    for departure, return_ in SEED_TRIPS:
        api(user).post(
            f"/api/v1/cases/{case_id}/travel-records",
            json={
                "destination_label": "Trip",
                "departure_date": departure,
                "return_date": return_,
                "date_confidence": "EXACT",
                "review_state": "CONFIRMED",
            },
        )
    return case_id


def _payloads(session: Session, case_id: str) -> dict[str, tuple[Any, ...]]:
    """Each requirement's displayed result as a comparable value: conclusion, the summary
    parameters and breakdown the screen renders, and the exact input versions it read. If any
    of these moves, the user is looking at something different."""
    rows = session.execute(
        select(RequirementDefinition.requirement_key, AssessmentResult)
        .join(AssessmentResult, AssessmentResult.requirement_id == RequirementDefinition.id)
        .where(
            AssessmentResult.case_id == case_id,
            AssessmentResult.currency.in_((Currency.CURRENT.value, Currency.STALE.value)),
        )
    ).all()
    payloads = {}
    for key, result in rows:
        links = sorted(
            (link.input_kind, str(link.input_version_id), link.input_key)
            for link in session.scalars(
                select(AssessmentInputLink).where(
                    AssessmentInputLink.assessment_result_id == result.id
                )
            )
        )
        payloads[key] = (
            result.conclusion,
            result.summary_code,
            repr(sorted(result.summary_parameters.items())),
            repr(result.calculation_breakdown),
            repr(result.limitations),
            tuple(links),
        )
    return payloads


def _stale_keys(session: Session, case_id: str) -> set[str]:
    return {
        key
        for key, result in session.execute(
            select(RequirementDefinition.requirement_key, AssessmentResult)
            .join(AssessmentResult, AssessmentResult.requirement_id == RequirementDefinition.id)
            .where(
                AssessmentResult.case_id == case_id,
                AssessmentResult.currency == Currency.STALE.value,
            )
        ).all()
    }


def _assert_no_under_fire(
    before: dict[str, tuple[Any, ...]],
    after: dict[str, tuple[Any, ...]],
    staled: set[str],
    change: str,
) -> None:
    moved = {key for key in before if key in after and before[key] != after[key]}
    missed = moved - staled
    assert not missed, (
        f"{change}: {sorted(missed)} produced different output after the change but were "
        f"never marked stale — they read CURRENT while their inputs had moved. Staled: "
        f"{sorted(staled)}"
    )


@_PROPERTY
@given(offset_days=st.integers(min_value=-45, max_value=45).filter(bool))
def test_moving_the_application_date_stales_everything_it_moves(
    api: Api, db_session: Session, offset_days: int
) -> None:
    case_id = _case(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _payloads(db_session, case_id)

    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={
            "application_date": (BASE_APPLICATION_DATE + timedelta(days=offset_days)).isoformat(),
            "expected_revision": current["revision"],
        },
    )
    staled = _stale_keys(db_session, case_id)

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    after = _payloads(db_session, case_id)

    _assert_no_under_fire(before, after, staled, f"application date {offset_days:+d} days")


@_PROPERTY
@given(
    trip_index=st.integers(min_value=0, max_value=len(SEED_TRIPS) - 1),
    shift_days=st.integers(min_value=-20, max_value=20).filter(bool),
)
def test_editing_a_trip_stales_everything_it_moves(
    api: Api, db_session: Session, trip_index: int, shift_days: int
) -> None:
    case_id = _case(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _payloads(db_session, case_id)

    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    record = records[trip_index]
    departure = date.fromisoformat(str(record["departure_date"]))
    return_ = date.fromisoformat(str(record["return_date"])) + timedelta(days=shift_days)
    if return_ < departure:
        return_ = departure
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": str(record["destination_label"]),
            "departure_date": departure.isoformat(),
            "return_date": return_.isoformat(),
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    staled = _stale_keys(db_session, case_id)

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    after = _payloads(db_session, case_id)

    _assert_no_under_fire(before, after, staled, f"trip {trip_index} return {shift_days:+d} days")


def test_removing_a_trip_stales_everything_it_moves(api: Api, db_session: Session) -> None:
    case_id = _case(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _payloads(db_session, case_id)

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[1]
    api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        params={"expected_revision": record["revision"]},
    )
    staled = _stale_keys(db_session, case_id)

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    after = _payloads(db_session, case_id)

    _assert_no_under_fire(before, after, staled, "trip removed")


def test_adding_a_trip_stales_everything_it_moves(api: Api, db_session: Session) -> None:
    case_id = _case(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _payloads(db_session, case_id)

    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "New trip",
            "departure_date": "2025-08-01",
            "return_date": "2025-08-20",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )
    staled = _stale_keys(db_session, case_id)

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    after = _payloads(db_session, case_id)

    _assert_no_under_fire(before, after, staled, "trip added")


def test_a_date_move_that_flips_an_upstream_conclusion_stales_the_composite(
    api: Api, db_session: Session
) -> None:
    """The composition edge, caught by behaviour rather than by declaration.

    The generated cases above cannot catch a missing composition edge, and it is worth being
    precise about why: their applicant was born in 1990, so `route.adult_applicant` concludes
    SUPPORTED at every application date they try. The composite's output never moves, so there
    is no under-fire to detect — the oracle is right and the fixture is simply too weak.

    The edge only bites when an upstream conclusion actually flips, which needs an applicant
    whose 18th birthday the application date can straddle. Route support is evaluated against
    *today* at confirmation, so the applicant must already be 18 for the case to activate:
    born 2008-08-01, an adult now, but 17 on an application date of 2026-07-15.

    `route.standard_section_6_1` reads no date and declares no date dependency. It is staled
    purely because the conclusion it composes moved. Remove the composition closure and this
    test fails while every declaration-based test still passes — which is the whole reason
    this file resolves nothing from declarations.
    """
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={**SUPPORTED_ANSWERS, "date_of_birth": "2008-08-01"},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _payloads(db_session, case_id)
    assert before["route.adult_applicant"][0] == "SUPPORTED"
    assert before["route.standard_section_6_1"][0] == "SUPPORTED"

    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2026-07-15", "expected_revision": current["revision"]},
    )
    staled = _stale_keys(db_session, case_id)

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    after = _payloads(db_session, case_id)

    # The upstream conclusion really did flip, so the composite really did move.
    assert after["route.adult_applicant"][0] == "NOT_CURRENTLY_SATISFIED"
    assert after["route.standard_section_6_1"][0] != before["route.standard_section_6_1"][0]
    assert "route.standard_section_6_1" in staled

    _assert_no_under_fire(before, after, staled, "application date across the 18th birthday")
