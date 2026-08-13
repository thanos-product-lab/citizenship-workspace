"""Deterministic date and absence primitives — the correctness core of the product.

Every window boundary and absence figure flows through these functions, so the three
things that break most live here **once and nowhere else**:

- the `+1 day` window (`window` / `physical_presence_date`) — RULES_SPEC §3-4;
- endpoint-exclusive day counting (`absent_dates`) — RULES_SPEC §5.1-5.2;
- union-not-sum totals (`absence_union` + `count_in_window`) — RULES_SPEC §5.2.

Pure and dependency-free: no I/O, no clock, no ORM. `subtract_years` implements the
`relativedelta` year semantics the spec mandates (RULES_SPEC §4.1) directly, so the only
clamp is 29 Feb → 28 Feb and the module carries no third-party dependency. Banding
boundaries are exact per RULES_SPEC §7.6/§7.7; the tables are the single owner of every
threshold so no rule re-derives one.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.requirements.domain import Conclusion

QUALIFYING_YEARS = 5
FINAL_YEAR_YEARS = 1
PRESENCE_SEARCH_HORIZON_DAYS = 90
TOTAL_ABSENCE_THRESHOLD_DAYS = 450
FINAL_YEAR_ABSENCE_THRESHOLD_DAYS = 90


def subtract_years(anchor: date, years: int) -> date:
    """`anchor` minus `years`, same month and day, clamped only when that day does not
    exist in the target year — i.e. 29 Feb → 28 Feb (RULES_SPEC §4.1). This is the
    `dateutil.relativedelta` year semantics the spec mandates, implemented directly so the
    rules carry no dependency. Age attainment (a different rule, §7.1) is *not* this."""
    try:
        return anchor.replace(year=anchor.year - years)
    except ValueError:
        # Only reachable for 29 Feb in a non-leap target year.
        return anchor.replace(year=anchor.year - years, month=2, day=28)


def add_years(anchor: date, years: int) -> date:
    """`anchor` plus `years`, same month and day, clamped only for 29 Feb → 28 Feb (the
    mirror of `subtract_years`; RULES_SPEC §4.1 semantics). Used for the holding-period
    earliest application date (status granted + 1 year, §7.3)."""
    try:
        return anchor.replace(year=anchor.year + years)
    except ValueError:
        return anchor.replace(year=anchor.year + years, month=2, day=28)


@dataclass(frozen=True)
class Window:
    """A closed date interval [start, end]. Both endpoints are inclusive (RULES_SPEC §4.2)."""

    start: date
    end: date

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


def window(application_date: date, years: int) -> Window:
    """The closed `years`-long interval ending on the application date. Start is
    `application_date - years + 1 day` — the +1 day the presence anchor and every absence
    total depend on (RULES_SPEC §3). A naive `- years` is wrong by exactly one day."""
    start = subtract_years(application_date, years) + timedelta(days=1)
    return Window(start=start, end=application_date)


def qualifying_window(application_date: date) -> Window:
    return window(application_date, QUALIFYING_YEARS)


def final_year_window(application_date: date) -> Window:
    return window(application_date, FINAL_YEAR_YEARS)


def physical_presence_date(application_date: date) -> date:
    """The anchor: the first day of the qualifying window, five years + 1 day before the
    application date. Presence on this exact day is the s.6(1) requirement (RULES_SPEC §7.5)."""
    return qualifying_window(application_date).start


def absent_dates(departure: date, return_: date) -> frozenset[date]:
    """The whole days outside the UK for one trip: `departure < d < return_`. The departure
    and return days are UK days and never count (RULES_SPEC §5.1), so a same-day or
    next-day trip contributes nothing. Returns empty if `return_ <= departure`."""
    if return_ <= departure:
        return frozenset()
    span = (return_ - departure).days - 1
    return frozenset(departure + timedelta(days=offset + 1) for offset in range(span))


def absence_union(trips: Iterable[tuple[date, date]]) -> frozenset[date]:
    """The set union of absent dates across trips. Union, not sum: overlapping trips never
    double-count and a duplicate trip changes nothing (RULES_SPEC §5.2), which is what makes
    the monotonicity invariant hold by construction."""
    union: set[date] = set()
    for departure, return_ in trips:
        union |= absent_dates(departure, return_)
    return frozenset(union)


def count_in_window(absent: frozenset[date], w: Window) -> int:
    """The count of absent dates falling inside the window. Intersection handles a trip that
    straddles a boundary with no special case — only its in-window days count (RULES_SPEC §5.3)."""
    return sum(1 for day in absent if w.contains(day))


def resolve_presence_date(
    trusted_absent: frozenset[date],
    application_date: date,
    horizon: int = PRESENCE_SEARCH_HORIZON_DAYS,
) -> date | None:
    """The nearest later application date, within `horizon` days, whose anchor is not a
    trusted absent date — or None if none resolves (RULES_SPEC §7.5). The trips are fixed;
    only the anchor moves as the date advances. The return day of a trip counts as present,
    so the first clear anchor can be a trip's own return day."""
    for offset in range(1, horizon + 1):
        candidate = application_date + timedelta(days=offset)
        if physical_presence_date(candidate) not in trusted_absent:
            return candidate
    return None


# --- Conclusion severity and absence banding -------------------------------

# Conclusion severity, least → most severe (RULES_SPEC §7.13). Higher rank = more severe.
# Owns the ordering used by the §6.2 sensitivity cap, banding monotonicity, and (later) the
# preparation aggregate — so "which conclusion is worse" is defined once.
_SEVERITY: dict[Conclusion, int] = {
    Conclusion.SUPPORTED: 0,
    Conclusion.NOT_YET_ASSESSED: 1,
    Conclusion.NEAR_THRESHOLD: 2,
    Conclusion.REQUIRES_JUDGEMENT: 3,
    Conclusion.INCOMPLETE: 4,
    Conclusion.INCONSISTENT: 5,
    Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED: 6,
    Conclusion.NOT_CURRENTLY_SATISFIED: 7,
}


def severity(conclusion: Conclusion) -> int:
    return _SEVERITY[conclusion]


def more_severe(candidate: Conclusion, than: Conclusion) -> bool:
    return severity(candidate) > severity(than)


@dataclass(frozen=True)
class Band:
    conclusion: Conclusion
    summary_code: str


# Total-absence bands (RULES_SPEC §7.6). Ascending inclusive upper bounds; the final band
# (upper=None) is open-ended. 450 is NEAR_THRESHOLD and 460 is REQUIRES_JUDGEMENT — not
# NOT_CURRENTLY_SATISFIED — because guidance normally exercises discretion up to 480.
_TOTAL_BANDS: tuple[tuple[int | None, Band], ...] = (
    (420, Band(Conclusion.SUPPORTED, "TOTAL_ABSENCES_WITHIN_THRESHOLD")),
    (450, Band(Conclusion.NEAR_THRESHOLD, "TOTAL_ABSENCES_NEAR_THRESHOLD")),
    (480, Band(Conclusion.REQUIRES_JUDGEMENT, "TOTAL_ABSENCES_DISCRETION_LIKELY")),
    (900, Band(Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, "TOTAL_ABSENCES_REVIEW_REQUIRED")),
    (None, Band(Conclusion.NOT_CURRENTLY_SATISFIED, "TOTAL_ABSENCES_EXCEEDED")),
)

# Final-year bands (RULES_SPEC §7.7): a proportionally wider near band (15 days), 90 the
# guidance limit, 180 the failure floor.
_FINAL_YEAR_BANDS: tuple[tuple[int | None, Band], ...] = (
    (75, Band(Conclusion.SUPPORTED, "FINAL_YEAR_WITHIN_THRESHOLD")),
    (90, Band(Conclusion.NEAR_THRESHOLD, "FINAL_YEAR_NEAR_THRESHOLD")),
    (100, Band(Conclusion.REQUIRES_JUDGEMENT, "FINAL_YEAR_DISCRETION_LIKELY")),
    (179, Band(Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, "FINAL_YEAR_REVIEW_REQUIRED")),
    (None, Band(Conclusion.NOT_CURRENTLY_SATISFIED, "FINAL_YEAR_EXCEEDED")),
)


def _band(days: int, table: tuple[tuple[int | None, Band], ...]) -> Band:
    for upper, band in table:
        if upper is None or days <= upper:
            return band
    raise AssertionError("unreachable: the final band is open-ended")


def band_total_absences(days: int) -> Band:
    return _band(days, _TOTAL_BANDS)


def band_final_year_absences(days: int) -> Band:
    return _band(days, _FINAL_YEAR_BANDS)
