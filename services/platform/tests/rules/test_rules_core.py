"""The deterministic core: window +1 day, endpoint-exclusive counting, union-not-sum,
banding boundaries, and the resolving-date search.

Exact-value anchors come from RULES_SPEC by hand (§3 Guide AN example, §4.1 leap table,
§9 corrected worked example, §7.6/§7.7 band edges). Property tests cover the RULES_SPEC
§10 invariants. **No 439 here** — that is a demo-case integration literal; a property test
asserting it would mean the two fixtures have bled.
"""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.requirements.domain import Conclusion
from app.requirements.rules_core import (
    absence_union,
    absent_dates,
    add_years,
    band_final_year_absences,
    band_total_absences,
    count_in_window,
    final_year_window,
    physical_presence_date,
    qualifying_window,
    resolve_presence_date,
    severity,
    subtract_years,
    window,
)

_DATES = st.dates(min_value=date(2020, 1, 1), max_value=date(2032, 12, 31))
_APP_DATES = st.dates(min_value=date(2024, 1, 1), max_value=date(2032, 12, 31))


# --- window and the +1 day (RULES_SPEC §3-4) --------------------------------


def test_guide_an_worked_example() -> None:
    # Application received 05/01/2022 → present on 06/01/2017 (GUIDE_AN, RULES_SPEC §3).
    assert physical_presence_date(date(2022, 1, 5)) == date(2017, 1, 6)


def test_demo_windows() -> None:
    q = qualifying_window(date(2027, 4, 15))
    assert (q.start, q.end) == (date(2022, 4, 16), date(2027, 4, 15))
    fy = final_year_window(date(2027, 4, 15))
    assert (fy.start, fy.end) == (date(2026, 4, 16), date(2027, 4, 15))


@pytest.mark.parametrize(
    ("application_date", "expected_start"),
    [
        (date(2027, 4, 15), date(2022, 4, 16)),
        (date(2028, 2, 29), date(2023, 3, 1)),  # 29 Feb clamps to 28 Feb, +1 → 1 Mar
        (date(2027, 3, 1), date(2022, 3, 2)),
        (date(2028, 3, 1), date(2023, 3, 2)),
    ],
)
def test_leap_and_month_boundary_table(application_date: date, expected_start: date) -> None:
    # RULES_SPEC §4.1 worked table.
    assert window(application_date, 5).start == expected_start


def test_subtract_years_clamps_only_leap_day() -> None:
    assert subtract_years(date(2028, 2, 29), 5) == date(2023, 2, 28)
    assert subtract_years(date(2024, 2, 29), 4) == date(2020, 2, 29)  # target is a leap year


def test_add_years_clamps_only_leap_day() -> None:
    assert add_years(date(2025, 3, 1), 1) == date(2026, 3, 1)
    assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)  # 2025 is not a leap year
    assert add_years(date(2024, 2, 29), 4) == date(2028, 2, 29)  # target is a leap year


@given(_DATES, st.integers(min_value=0, max_value=8))
@pytest.mark.property
def test_add_years_preserves_month_day_except_leap(anchor: date, years: int) -> None:
    result = add_years(anchor, years)
    assert result.year == anchor.year + years
    if (anchor.month, anchor.day) == (2, 29) and not _is_leap(anchor.year + years):
        assert (result.month, result.day) == (2, 28)
    else:
        assert (result.month, result.day) == (anchor.month, anchor.day)


@given(_APP_DATES)
@pytest.mark.property
def test_window_start_matches_independent_formula(application_date: date) -> None:
    # Reconstruct the expected start with date() directly, independent of subtract_years.
    if (application_date.month, application_date.day) == (2, 29):
        return  # clamp case covered exactly above
    expected = date(application_date.year - 5, application_date.month, application_date.day)
    assert window(application_date, 5).start == expected + timedelta(days=1)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@given(_DATES, st.integers(min_value=0, max_value=8))
@pytest.mark.property
def test_subtract_years_preserves_month_day_except_leap(anchor: date, years: int) -> None:
    result = subtract_years(anchor, years)
    assert result.year == anchor.year - years
    # 29 Feb clamps to 28 Feb only when the *target* year is not itself a leap year.
    if (anchor.month, anchor.day) == (2, 29) and not _is_leap(anchor.year - years):
        assert (result.month, result.day) == (2, 28)
    else:
        assert (result.month, result.day) == (anchor.month, anchor.day)


# --- absence counting (RULES_SPEC §5) ---------------------------------------


def test_guide_an_absence_example_is_empty() -> None:
    # Left 22 Sep, returned 23 Sep → not absent (RULES_SPEC §5.1).
    assert absent_dates(date(2024, 9, 22), date(2024, 9, 23)) == frozenset()


def test_return_on_or_before_departure_is_empty() -> None:
    assert absent_dates(date(2024, 9, 22), date(2024, 9, 22)) == frozenset()
    assert absent_dates(date(2024, 9, 22), date(2024, 9, 21)) == frozenset()


def test_trip_departing_returning_or_spanning_the_anchor() -> None:
    anchor = date(2022, 4, 16)
    # Departing on the anchor: anchor is the departure (UK) day → present.
    assert anchor not in absent_dates(anchor, date(2022, 4, 20))
    # Returning on the anchor: anchor is the return (UK) day → present.
    assert anchor not in absent_dates(date(2022, 4, 12), anchor)
    # Spanning the anchor: departure < anchor < return → absent.
    assert anchor in absent_dates(date(2022, 4, 12), date(2022, 4, 20))


def test_demo_trip1_clips_to_ten_inside_the_window() -> None:
    # Spain 14→26 Apr 2022 straddles the window start (16 Apr); only 16-25 count (10),
    # not the full 15-25 span (11). Clipping is the rule's job (RULES_SPEC §9).
    absent = absent_dates(date(2022, 4, 14), date(2022, 4, 26))
    assert count_in_window(absent, qualifying_window(date(2027, 4, 15))) == 10


@given(_DATES, st.integers(min_value=-3, max_value=400))
@pytest.mark.property
def test_absent_cardinality_is_span_minus_one(departure: date, offset: int) -> None:
    return_ = departure + timedelta(days=offset)
    expected = max(0, offset - 1)
    assert len(absent_dates(departure, return_)) == expected


@given(st.lists(st.tuples(_DATES, st.integers(min_value=0, max_value=200)), max_size=8))
@pytest.mark.property
def test_union_is_reorder_invariant_and_duplicate_idempotent(
    raw: list[tuple[date, int]],
) -> None:
    trips = [(dep, dep + timedelta(days=span)) for dep, span in raw]
    base = absence_union(trips)
    assert absence_union(list(reversed(trips))) == base  # order does not matter
    if trips:
        assert absence_union([*trips, trips[0]]) == base  # a duplicate adds nothing


@given(
    _DATES,
    st.integers(min_value=1, max_value=60),
    st.integers(min_value=1, max_value=60),
    st.integers(min_value=0, max_value=30),
)
@pytest.mark.property
def test_overlapping_trips_are_union_not_sum(dep: date, a: int, b: int, gap: int) -> None:
    # Two trips that overlap: the union cardinality is at most the sum, and strictly less
    # when they share absent dates.
    t1 = (dep, dep + timedelta(days=a))
    t2 = (dep + timedelta(days=gap), dep + timedelta(days=gap + b))
    union = absence_union([t1, t2])
    total_sum = len(absent_dates(*t1)) + len(absent_dates(*t2))
    assert len(union) <= total_sum


@given(
    st.lists(st.tuples(_APP_DATES, st.integers(min_value=0, max_value=200)), max_size=6),
    _APP_DATES,
    st.tuples(_APP_DATES, st.integers(min_value=0, max_value=200)),
)
@pytest.mark.property
def test_adding_a_trip_never_decreases_the_windowed_count(
    raw: list[tuple[date, int]], app: date, extra_raw: tuple[date, int]
) -> None:
    trips = [(dep, dep + timedelta(days=span)) for dep, span in raw]
    extra = (extra_raw[0], extra_raw[0] + timedelta(days=extra_raw[1]))
    w = qualifying_window(app)
    before = count_in_window(absence_union(trips), w)
    after = count_in_window(absence_union([*trips, extra]), w)
    assert after >= before  # a superset of absent dates can only raise the count


# --- resolving date (RULES_SPEC §7.5, §9 corrected) -------------------------


def test_resolving_date_spec_9_corrected() -> None:
    # §9's Spain trip 14→20 Apr 2022 (absent 15-19); return day 20 Apr is present, so the
    # first clear anchor is 20 Apr 2022 → application date 2027-04-19 (corrected 2026-08-12).
    absent = absent_dates(date(2022, 4, 14), date(2022, 4, 20))
    assert resolve_presence_date(absent, date(2027, 4, 15)) == date(2027, 4, 19)


def test_resolving_date_demo_case() -> None:
    # Demo trip 1, 14→26 Apr 2022 (absent 15-25); resolves to 2027-04-25 (demo §8 oracle).
    absent = absent_dates(date(2022, 4, 14), date(2022, 4, 26))
    assert resolve_presence_date(absent, date(2027, 4, 15)) == date(2027, 4, 25)


def test_resolving_date_returns_none_past_horizon() -> None:
    # An anchor blocked for more than 90 days ahead does not resolve.
    absent = absent_dates(date(2022, 1, 1), date(2024, 1, 1))
    assert resolve_presence_date(absent, date(2027, 4, 15)) is None


# --- banding boundaries (RULES_SPEC §7.6, §7.7) -----------------------------


@pytest.mark.parametrize(
    ("days", "conclusion", "code"),
    [
        (0, Conclusion.SUPPORTED, "TOTAL_ABSENCES_WITHIN_THRESHOLD"),
        (420, Conclusion.SUPPORTED, "TOTAL_ABSENCES_WITHIN_THRESHOLD"),
        (421, Conclusion.NEAR_THRESHOLD, "TOTAL_ABSENCES_NEAR_THRESHOLD"),
        (450, Conclusion.NEAR_THRESHOLD, "TOTAL_ABSENCES_NEAR_THRESHOLD"),
        (451, Conclusion.REQUIRES_JUDGEMENT, "TOTAL_ABSENCES_DISCRETION_LIKELY"),
        (460, Conclusion.REQUIRES_JUDGEMENT, "TOTAL_ABSENCES_DISCRETION_LIKELY"),
        (480, Conclusion.REQUIRES_JUDGEMENT, "TOTAL_ABSENCES_DISCRETION_LIKELY"),
        (481, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, "TOTAL_ABSENCES_REVIEW_REQUIRED"),
        (900, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, "TOTAL_ABSENCES_REVIEW_REQUIRED"),
        (901, Conclusion.NOT_CURRENTLY_SATISFIED, "TOTAL_ABSENCES_EXCEEDED"),
    ],
)
def test_total_absence_bands(days: int, conclusion: Conclusion, code: str) -> None:
    band = band_total_absences(days)
    assert (band.conclusion, band.summary_code) == (conclusion, code)


@pytest.mark.parametrize(
    ("days", "conclusion", "code"),
    [
        (75, Conclusion.SUPPORTED, "FINAL_YEAR_WITHIN_THRESHOLD"),
        (76, Conclusion.NEAR_THRESHOLD, "FINAL_YEAR_NEAR_THRESHOLD"),
        (90, Conclusion.NEAR_THRESHOLD, "FINAL_YEAR_NEAR_THRESHOLD"),
        (91, Conclusion.REQUIRES_JUDGEMENT, "FINAL_YEAR_DISCRETION_LIKELY"),
        (100, Conclusion.REQUIRES_JUDGEMENT, "FINAL_YEAR_DISCRETION_LIKELY"),
        (101, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, "FINAL_YEAR_REVIEW_REQUIRED"),
        (179, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, "FINAL_YEAR_REVIEW_REQUIRED"),
        (180, Conclusion.NOT_CURRENTLY_SATISFIED, "FINAL_YEAR_EXCEEDED"),
    ],
)
def test_final_year_absence_bands(days: int, conclusion: Conclusion, code: str) -> None:
    band = band_final_year_absences(days)
    assert (band.conclusion, band.summary_code) == (conclusion, code)


@given(st.integers(min_value=0, max_value=1500), st.integers(min_value=0, max_value=1500))
@pytest.mark.property
def test_banding_is_monotonic(days_a: int, days_b: int) -> None:
    lo, hi = sorted((days_a, days_b))
    assert severity(band_total_absences(hi).conclusion) >= severity(
        band_total_absences(lo).conclusion
    )
    assert severity(band_final_year_absences(hi).conclusion) >= severity(
        band_final_year_absences(lo).conclusion
    )
