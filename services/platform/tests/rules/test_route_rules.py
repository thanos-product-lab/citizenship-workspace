"""Route rules: band tests (both sides of every boundary) + property tests.

The property-marked tests are the Hypothesis suite `just test-rules` runs. They
cover the two properties these rules touch: determinism (same inputs → same
outcome) and the adulthood boundary / monotonicity in the reference date. The adult
rule does date arithmetic, so leap-year and exact-18 boundaries are covered too.
"""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.requirements.domain import Conclusion
from app.requirements.route_rules import (
    ROUTE_ADULT_CONFIRMED,
    ROUTE_APPLICANT_UNDER_18,
    ROUTE_MAY_BE_BRITISH,
    ROUTE_PREREQUISITES_UNMET,
    ROUTE_SPOUSE_UNSUPPORTED,
    ROUTE_STANDARD_CONFIRMED,
    STATUS_TYPE_SUPPORTED,
    STATUS_TYPE_UNSUPPORTED,
    RuleOutcome,
    age_in_years,
    evaluate_adult,
    evaluate_route_support,
    evaluate_standard_section_6_1,
    evaluate_supported_status,
)

REF = date(2026, 7, 27)


def _adult() -> RuleOutcome:
    return evaluate_adult(date(2000, 1, 1), reference_date=REF)


def _supported_status() -> RuleOutcome:
    return evaluate_supported_status("ILR")


# --- route.adult_applicant (§7.1) -----------------------------------------


def test_adult_missing_dob_is_not_yet_assessed() -> None:
    r = evaluate_adult(None, reference_date=REF)
    assert r.conclusion is Conclusion.NOT_YET_ASSESSED
    assert r.summary_code is None


def test_adult_exactly_18_today_is_supported() -> None:
    # 18th birthday lands exactly on the reference date.
    r = evaluate_adult(date(2008, 7, 27), reference_date=REF)
    assert r.conclusion is Conclusion.SUPPORTED
    assert r.summary_code == ROUTE_ADULT_CONFIRMED


def test_adult_one_day_short_of_18_is_not_satisfied() -> None:
    # 18th birthday is tomorrow → 17 today.
    r = evaluate_adult(date(2008, 7, 28), reference_date=REF)
    assert r.conclusion is Conclusion.NOT_CURRENTLY_SATISFIED
    assert r.summary_code == ROUTE_APPLICANT_UNDER_18


def test_age_handles_leap_day_birthday() -> None:
    # Deliberate convention: a 29-Feb birthday attains its age on 1 March in a
    # non-leap year (UK age-attainment reading), which differs from RULES_SPEC §4.1's
    # relativedelta window-clamping (28 Feb). Pending an explicit §7.1 spec note on
    # which convention age uses; this test pins the current behaviour on purpose.
    dob = date(2008, 2, 29)
    assert age_in_years(dob, date(2026, 2, 28)) == 17  # birthday not yet reached
    assert age_in_years(dob, date(2026, 3, 1)) == 18  # completes 1 Mar in a non-leap year


# --- route.supported_status (§7.2) ----------------------------------------


@pytest.mark.parametrize("status_type", ["ILR", "ILE", "EU_SETTLED_STATUS"])
def test_status_supported_types(status_type: str) -> None:
    r = evaluate_supported_status(status_type)
    assert r.conclusion is Conclusion.SUPPORTED
    assert r.summary_code == STATUS_TYPE_SUPPORTED


def test_status_other_needs_professional_review() -> None:
    r = evaluate_supported_status("OTHER")
    assert r.conclusion is Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED
    assert r.summary_code == STATUS_TYPE_UNSUPPORTED


@pytest.mark.parametrize("status_type", ["UNKNOWN", None])
def test_status_unknown_or_absent_is_not_yet_assessed(status_type: str | None) -> None:
    r = evaluate_supported_status(status_type)
    assert r.conclusion is Conclusion.NOT_YET_ASSESSED
    assert r.summary_code is None


# --- route.standard_section_6_1 (§7.2b) -----------------------------------


def test_composite_unconfirmed_is_not_yet_assessed() -> None:
    r = evaluate_standard_section_6_1(
        married_to_british_citizen=False,
        may_already_be_british=False,
        adult=_adult(),
        status=_supported_status(),
        profile_confirmed=False,
    )
    assert r.conclusion is Conclusion.NOT_YET_ASSESSED


def test_composite_all_clear_is_supported() -> None:
    r = evaluate_standard_section_6_1(
        married_to_british_citizen=False,
        may_already_be_british=False,
        adult=_adult(),
        status=_supported_status(),
        profile_confirmed=True,
    )
    assert r.conclusion is Conclusion.SUPPORTED
    assert r.summary_code == ROUTE_STANDARD_CONFIRMED


def test_composite_spouse_route_takes_precedence_even_over_failed_prerequisites() -> None:
    # Married AND under-18 AND unsupported status: spouse still wins (checked first).
    r = evaluate_standard_section_6_1(
        married_to_british_citizen=True,
        may_already_be_british=True,
        adult=evaluate_adult(date(2020, 1, 1), reference_date=REF),
        status=evaluate_supported_status("OTHER"),
        profile_confirmed=True,
    )
    assert r.conclusion is Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED
    assert r.summary_code == ROUTE_SPOUSE_UNSUPPORTED


def test_composite_may_be_british_when_not_spouse() -> None:
    r = evaluate_standard_section_6_1(
        married_to_british_citizen=False,
        may_already_be_british=True,
        adult=_adult(),
        status=_supported_status(),
        profile_confirmed=True,
    )
    assert r.conclusion is Conclusion.REQUIRES_JUDGEMENT
    assert r.summary_code == ROUTE_MAY_BE_BRITISH


@pytest.mark.parametrize(
    ("adult", "status"),
    [
        (evaluate_adult(date(2020, 1, 1), reference_date=REF), evaluate_supported_status("ILR")),
        (evaluate_adult(date(2000, 1, 1), reference_date=REF), evaluate_supported_status("OTHER")),
    ],
)
def test_composite_prerequisites_unmet(adult: RuleOutcome, status: RuleOutcome) -> None:
    r = evaluate_standard_section_6_1(
        married_to_british_citizen=False,
        may_already_be_british=False,
        adult=adult,
        status=status,
        profile_confirmed=True,
    )
    assert r.conclusion is Conclusion.NOT_CURRENTLY_SATISFIED
    assert r.summary_code == ROUTE_PREREQUISITES_UNMET


# --- properties (Hypothesis) ----------------------------------------------

_STATUS = st.sampled_from(["ILR", "ILE", "EU_SETTLED_STATUS", "OTHER", "UNKNOWN", None])
_TRISTATE = st.sampled_from([True, False, None])
_DATES = st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))


@pytest.mark.property
@given(
    dob=st.none() | _DATES,
    status_type=_STATUS,
    married=_TRISTATE,
    may_british=_TRISTATE,
    reference=_DATES,
    confirmed=st.booleans(),
)
def test_route_support_is_deterministic(
    dob: date | None,
    status_type: str | None,
    married: bool | None,
    may_british: bool | None,
    reference: date,
    confirmed: bool,
) -> None:
    def run() -> object:
        return evaluate_route_support(
            date_of_birth=dob,
            status_type=status_type,
            married_to_british_citizen=married,
            may_already_be_british=may_british,
            reference_date=reference,
            profile_confirmed=confirmed,
        )

    assert run() == run()


@pytest.mark.property
@given(dob=_DATES, reference=_DATES)
def test_adult_supported_iff_at_least_18(dob: date, reference: date) -> None:
    outcome = evaluate_adult(dob, reference_date=reference)
    is_supported = outcome.conclusion is Conclusion.SUPPORTED
    assert is_supported == (age_in_years(dob, reference) >= 18)


@pytest.mark.property
@given(dob=_DATES, r1=_DATES, r2=_DATES)
def test_adulthood_is_monotonic_in_reference_date(dob: date, r1: date, r2: date) -> None:
    # Once an adult, always an adult: a later reference date never revokes it.
    early, late = sorted([r1, r2])
    if evaluate_adult(dob, reference_date=early).conclusion is Conclusion.SUPPORTED:
        assert evaluate_adult(dob, reference_date=late).conclusion is Conclusion.SUPPORTED
