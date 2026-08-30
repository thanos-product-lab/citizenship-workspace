"""Every user-entered date falls inside a sane calendar range.

Written after the M7 gate walkthrough, where a route profile carrying
`date_of_birth = 0995-12-11` and `status_granted_on = 0024-09-11` was assessed without
hesitation: `route.adult_applicant` concluded **SUPPORTED** for an applicant 1031 years
old, and `status.holding_period` **SUPPORTED** on two millennia of settled status. No rule
was wrong. Every one did exactly what it was told with the numbers it was given.

That is the failure directive 7 names — the most confident possible answer, derived from a
typo — and it survived 793 backend tests, because every fixture in the suite holds a
sensible date. It took a person typing into a form to find it.

The bound is validation, not a rule: `app/shared/dates.py` says why, and why rejecting is
right where escalating would be wrong.
"""

from datetime import date

import pytest
from httpx import Response

from app.shared.dates import MAX_ENTERED_DATE, MIN_ENTERED_DATE
from tests.conftest import Api

#: The literal values from the walkthrough. Kept verbatim rather than reduced to "some old
#: date", because the point is the shape of a real slip: a year typed into a native date
#: field that took the digits it was given.
WALKTHROUGH_DOB = "0995-12-11"
WALKTHROUGH_GRANT = "0024-09-11"


def _case(api: Api, user: str = "user_a", *, active: bool = False) -> str:
    """A case. `active=True` also confirms the route profile, because writing a travel
    record needs an ACTIVE case and a DRAFT one answers 409 before validation runs — which
    would make a date-range test pass for a reason that has nothing to do with dates."""
    case_id = str(api(user).post("/api/v1/cases", json={"title": "Dates"}).json()["id"])
    if active:
        _profile(api, user, case_id)
        api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    return case_id


def _profile(api: Api, user: str, case_id: str, **overrides: object) -> Response:
    body = {
        "date_of_birth": "1990-04-12",
        "status_type": "ILR",
        "status_granted_on": "2019-03-01",
        "married_to_british_citizen": False,
        "may_already_be_british": False,
    }
    body.update(overrides)
    response: Response = api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=body)
    return response


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("date_of_birth", WALKTHROUGH_DOB),
        ("status_granted_on", WALKTHROUGH_GRANT),
        ("date_of_birth", "1899-12-31"),
        ("status_granted_on", "1899-12-31"),
    ],
)
def test_a_route_profile_date_outside_the_calendar_range_is_refused(
    field: str, value: str, api: Api
) -> None:
    """422 naming the field, not an assessment nobody should trust."""
    case_id = _case(api)
    response = _profile(api, "user_a", case_id, **{field: value})

    assert response.status_code == 422
    assert field in response.text


def test_the_boundary_dates_themselves_are_accepted(api: Api) -> None:
    """`ge`/`le`, not `gt`/`lt`. A bound that excluded its own endpoints would be a
    different bound than the one documented, and the off-by-one would only ever show up
    on the one date nobody tries."""
    case_id = _case(api)
    response = _profile(
        api,
        "user_a",
        case_id,
        date_of_birth=MIN_ENTERED_DATE.isoformat(),
        status_granted_on=MIN_ENTERED_DATE.isoformat(),
    )

    assert response.status_code == 200


def test_a_plausible_but_wrong_date_is_still_accepted_and_assessed(api: Api) -> None:
    """The bound is calendar sanity, **not** plausibility, and that distinction is load-
    bearing. A 2019 date of birth is a real possibility for a real applicant who is seven
    years old, and the *rule* is what must say so — moving that judgement into schema
    validation would hide it from the rules spec and version it with nothing."""
    case_id = _case(api)
    response = _profile(api, "user_a", case_id, date_of_birth="2019-04-12")

    assert response.status_code == 200


@pytest.mark.parametrize("field", ["departure_date", "return_date"])
def test_a_travel_record_date_outside_the_range_is_refused(field: str, api: Api) -> None:
    """Trips were unbounded entirely. A trip in year 24 persisted, and its absence
    arithmetic then ran against a qualifying window it could never intersect — so the
    total was silently correct about a journey nobody took."""
    case_id = _case(api, active=True)
    body = {
        "destination_label": "Greece",
        "departure_date": "2024-06-05",
        "return_date": "2024-07-15",
        field: WALKTHROUGH_GRANT,
    }
    response = api("user_a").post(f"/api/v1/cases/{case_id}/travel-records", json=body)

    assert response.status_code == 422
    assert field in response.text


def test_the_csv_importer_applies_the_same_range(api: Api) -> None:
    """Two paths write travel records, and a date one refuses must not be a date the other
    accepts. The importer reports it as a row diagnostic rather than a 422, because it
    reports every bad row at once instead of failing the file on the first."""
    case_id = _case(api, active=True)
    csv = (
        "destination_label,departure_date,return_date,date_confidence\n"
        f"Greece,{WALKTHROUGH_GRANT},2024-07-15,EXACT\n"
    )
    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/import", json={"content": csv}
    )

    assert response.status_code in (200, 422)
    assert "DATE_OUT_OF_RANGE" in response.text


def test_the_application_date_shares_the_one_range() -> None:
    """`MIN_APPLICATION_DATE` predates this and is now an alias. Two ranges that drifted
    apart would mean a date the profile accepts and the simulator refuses, with nothing to
    say which was right."""
    from app.residence.schemas import MAX_APPLICATION_DATE, MIN_APPLICATION_DATE

    assert (MIN_APPLICATION_DATE, MAX_APPLICATION_DATE) == (MIN_ENTERED_DATE, MAX_ENTERED_DATE)


def test_the_range_is_wide_enough_to_be_a_sanity_bound() -> None:
    """A guard against someone later "tightening" this into a plausibility rule. If the
    floor ever needs to move above 1900, that is a domain decision and belongs in
    DETERMINISTIC_RULES_SPEC.md with a rule version behind it, not here."""
    assert date(1900, 1, 1) >= MIN_ENTERED_DATE
    assert date(2100, 1, 1) <= MAX_ENTERED_DATE
