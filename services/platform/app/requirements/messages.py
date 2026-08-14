"""Deterministic plain-language rendering of the codes a rule emits.

Every user-visible sentence about an assessment is produced here, from a `(code,
parameters)` pair, by a pure function. **No model is involved and none ever will be**
(CLAUDE.md §2.2): a summary code is part of the rule's output, so its wording is part of
the deterministic contract, not something generated per request. The API returns the
code and its parameters *alongside* the rendered text, so a client can key layout off
the code and the text is never the only machine-readable signal.

Three registries, one per code family:

- `SUMMARY_TEMPLATES`      — `AssessmentResult.summary_code` + `.summary_parameters`
- `LIMITATION_TEMPLATES`   — `AssessmentResult.limitations[].code` + `.message_parameters`
- `NEXT_ACTION_TEMPLATES`  — `AssessmentResult.next_actions[].code` + `.label_parameters`
- `STALE_REASON_TEMPLATES` — `AssessmentResult.stale_reason_code`

Two rules the copy in this module must keep:

1. **Never frame a threshold gap as headroom.** "439 confirmed days against a threshold
   of 450", never "11 days remaining" — the latter is advice, and this product does not
   give advice (CLAUDE.md §1).
2. **Always say whose days a figure counts.** `summary_parameters` carries both `days`
   (confirmed records only) and `provisional_days` (every active record). The word
   *confirmed* is load-bearing, and where the two differ the sentence says so — an
   unconfirmed trip's days must never read as established fact (CLAUDE.md §2.1).

An unknown code is rendered as `None`, not as an invented sentence: the caller shows the
structured fields alone rather than guessing. `test_messages.py` asserts every code the
rules can emit has a template, so `None` means a genuine packaging bug, never routine.
"""

from collections.abc import Callable
from datetime import date

Parameters = dict[str, object]

# A template is a pure function of the code's parameters. Kept as a plain Callable
# (not a Protocol) so the lambdas below are checked structurally by position.
_Template = Callable[[Parameters], str]


# --- parameter helpers ------------------------------------------------------

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def format_date(value: object) -> str:
    """An ISO date string → "15 April 2027" (UI/UX §13.3: dates get deliberate
    emphasis, and an ISO string in a sentence reads as machine output). A value that
    is not a parseable date is returned unchanged rather than raising — a missing
    parameter must degrade to something honest, never to a 500 on a read path."""
    if isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return value
    else:
        return str(value)
    return f"{parsed.day} {_MONTHS[parsed.month - 1]} {parsed.year}"


def _days(value: object) -> str:
    return f"{value} day" if value == 1 else f"{value} days"


def _int(p: Parameters, key: str) -> int | None:
    value = p.get(key)
    return value if isinstance(value, int) else None


# --- summary codes ----------------------------------------------------------


def _absence_summary(p: Parameters, *, period: str, verdict: str) -> str:
    """Shared body for the ten total/final-year band codes. States the confirmed figure
    against the threshold, then — only when they differ — the provisional figure, naming
    it as unconfirmed. `days` is always the trusted total; `provisional_days` includes
    records that have not been confirmed."""
    confirmed = _int(p, "days")
    threshold = _int(p, "threshold")
    provisional = _int(p, "provisional_days")

    sentence = f"{_days(confirmed)} outside the UK {period}, from confirmed travel records"
    if threshold is not None:
        sentence += f", against a threshold of {threshold}"
    sentence += f". {verdict}"

    if provisional is not None and confirmed is not None and provisional > confirmed:
        extra = provisional - confirmed
        sentence += (
            f" Records you have not confirmed would add {_days(extra)},"
            f" bringing the total to {provisional}."
        )
    return sentence


SUMMARY_TEMPLATES: dict[str, _Template] = {
    # route.adult_applicant (§7.1)
    "ROUTE_ADULT_CONFIRMED": lambda p: (
        f"You are 18 or over on {format_date(p.get('reference_date'))}, "
        "your proposed application date."
    ),
    "ROUTE_APPLICANT_UNDER_18": lambda p: (
        f"You are under 18 on {format_date(p.get('reference_date'))}, your proposed "
        "application date. Naturalisation is for adults; children register instead, "
        "which this workspace does not cover."
    ),
    # route.supported_status (§7.2)
    "STATUS_TYPE_SUPPORTED": lambda p: (
        "Your settled status is one of the three this route accepts: indefinite leave "
        "to remain, indefinite leave to enter, or EU settled status."
    ),
    "STATUS_TYPE_UNSUPPORTED": lambda p: (
        "Your status is not one this workspace can assess. Only indefinite leave to "
        "remain, indefinite leave to enter, and EU settled status are covered."
    ),
    # route.standard_section_6_1 (§7.2b)
    "ROUTE_STANDARD_CONFIRMED": lambda p: (
        "Your case fits the standard five-year route under Section 6(1)."
    ),
    "ROUTE_SPOUSE_UNSUPPORTED": lambda p: (
        "You told us you are married to a British citizen. That is the spouse route "
        "under Section 6(2), which this workspace does not assess."
    ),
    "ROUTE_MAY_BE_BRITISH": lambda p: (
        "You told us you may already be a British citizen. If that is right, you would "
        "not need to naturalise at all — this needs a person to look at."
    ),
    "ROUTE_PREREQUISITES_UNMET": lambda p: (
        "The standard five-year route depends on being an adult and holding a settled "
        "status this route accepts. At least one of those is not currently met."
    ),
    # status.holding_period (§7.3)
    "STATUS_PERIOD_SATISFIED": lambda p: (
        "You will have held your settled status free of immigration time restrictions "
        "for at least 12 months by your proposed application date. The earliest date "
        f"that holds is {format_date(p.get('earliest_application_date'))}."
    ),
    "STATUS_PERIOD_NARROW_MARGIN": lambda p: (
        "Your proposed application date falls within a week of the earliest date the "
        f"12-month holding period allows, {format_date(p.get('earliest_application_date'))}. "
        "Guidance does not state this boundary to the day."
    ),
    "STATUS_PERIOD_NOT_YET_MET": lambda p: (
        "Your proposed application date is before the earliest date the 12-month "
        "holding period allows, "
        f"{format_date(p.get('earliest_application_date'))}."
    ),
    # residence.qualifying_period (§7.4) — a calculation, not a test. Its dates live in
    # calculation_breakdown rather than summary_parameters, so this sentence names none.
    "QUALIFYING_PERIOD_DERIVED": lambda p: (
        "Your five-year qualifying period is derived from your proposed application "
        "date: the five years ending on that date, counted from the day after the "
        "same date five years earlier."
    ),
    # residence.physical_presence_start_date (§7.5)
    "PRESENCE_CONFIRMED": lambda p: (
        "Your confirmed travel records place you in the UK on "
        f"{format_date(p.get('physical_presence_date'))}, the first day of your "
        "qualifying period."
    ),
    "PRESENCE_UNCERTAIN": lambda p: (
        "A travel record you have not confirmed covers "
        f"{format_date(p.get('physical_presence_date'))}, the first day of your "
        "qualifying period. Until it is confirmed, presence on that day is unresolved."
    ),
    "PRESENCE_NOT_SUPPORTED": lambda p: (
        "Your confirmed travel records place you outside the UK on "
        f"{format_date(p.get('physical_presence_date'))}, the first day of your "
        "qualifying period."
        + (
            " The earliest later application date whose first day is clear of confirmed "
            f"absence is {format_date(p.get('resolving_application_date'))}."
            if p.get("resolving_application_date")
            else " No later date within the next 90 days clears that day."
        )
    ),
    # residence.total_absences (§7.6)
    "TOTAL_ABSENCES_WITHIN_THRESHOLD": lambda p: _absence_summary(
        p,
        period="across your five-year qualifying period",
        verdict="That is within the standard threshold.",
    ),
    "TOTAL_ABSENCES_NEAR_THRESHOLD": lambda p: _absence_summary(
        p,
        period="across your five-year qualifying period",
        verdict="That is close to the standard threshold.",
    ),
    "TOTAL_ABSENCES_DISCRETION_LIKELY": lambda p: _absence_summary(
        p,
        period="across your five-year qualifying period",
        verdict="That is over the standard threshold, in the range where guidance normally "
        "allows discretion to be exercised.",
    ),
    "TOTAL_ABSENCES_REVIEW_REQUIRED": lambda p: _absence_summary(
        p,
        period="across your five-year qualifying period",
        verdict="That is well over the standard threshold. This needs professional review.",
    ),
    "TOTAL_ABSENCES_EXCEEDED": lambda p: _absence_summary(
        p,
        period="across your five-year qualifying period",
        verdict="That is far over the standard threshold.",
    ),
    "TOTAL_ABSENCES_UNCONFIRMED_REVIEW": lambda p: _absence_summary(
        p,
        period="across your five-year qualifying period",
        verdict="Your confirmed records are within the threshold, but records you have not "
        "confirmed would change that conclusion, so it cannot be settled yet.",
    ),
    # residence.final_year_absences (§7.7)
    "FINAL_YEAR_WITHIN_THRESHOLD": lambda p: _absence_summary(
        p,
        period="in the final 12 months",
        verdict="That is within the standard threshold.",
    ),
    "FINAL_YEAR_NEAR_THRESHOLD": lambda p: _absence_summary(
        p,
        period="in the final 12 months",
        verdict="That is close to the standard threshold.",
    ),
    "FINAL_YEAR_DISCRETION_LIKELY": lambda p: _absence_summary(
        p,
        period="in the final 12 months",
        verdict="That is over the standard threshold, in the range where guidance normally "
        "allows discretion to be exercised.",
    ),
    "FINAL_YEAR_REVIEW_REQUIRED": lambda p: _absence_summary(
        p,
        period="in the final 12 months",
        verdict="That is well over the standard threshold. This needs professional review.",
    ),
    "FINAL_YEAR_EXCEEDED": lambda p: _absence_summary(
        p,
        period="in the final 12 months",
        verdict="That is far over the standard threshold.",
    ),
    "FINAL_YEAR_UNCONFIRMED_REVIEW": lambda p: _absence_summary(
        p,
        period="in the final 12 months",
        verdict="Your confirmed records are within the threshold, but records you have not "
        "confirmed would change that conclusion, so it cannot be settled yet.",
    ),
    # residence.travel_consistency (§7.8) — a data-quality verdict, no figures attached.
    "TRAVEL_RECORDS_CONSISTENT": lambda p: (
        "Your travel records are internally consistent: no overlaps, no conflicting "
        "dates, and no uncertain dates inside the qualifying period."
    ),
    "TRAVEL_RECORDS_CONFLICT": lambda p: (
        "At least one travel record inside your qualifying period has conflicting "
        "dates from different sources. Absence totals cannot be relied on until that "
        "is resolved."
    ),
    "TRAVEL_RECORDS_OVERLAP": lambda p: (
        "Two or more of your travel records cover the same days. One of them is "
        "probably a duplicate or has the wrong dates."
    ),
    "TRAVEL_RECORDS_UNCERTAIN": lambda p: (
        "At least one travel record inside your qualifying period has dates marked as "
        "estimated or unknown, so your absence totals are not yet settled."
    ),
}


# --- limitation codes -------------------------------------------------------


def _unconfirmed_records(p: Parameters) -> str:
    """One code, two parameter shapes, because two rules raise it: the absence rules pass
    `trusted_days`/`provisional_days`, physical presence passes `physical_presence_date`.
    Branch on what is present rather than assuming either."""
    trusted = _int(p, "trusted_days")
    provisional = _int(p, "provisional_days")
    if trusted is not None and provisional is not None:
        return (
            f"Your confirmed records total {_days(trusted)}. Including records you have "
            f"not confirmed would make it {provisional}, which lands in a different band."
        )
    if p.get("physical_presence_date"):
        return (
            "A travel record you have not confirmed covers "
            f"{format_date(p.get('physical_presence_date'))}, so presence on the first "
            "day of your qualifying period is unresolved."
        )
    return "Records you have not confirmed would change this conclusion."


LIMITATION_TEMPLATES: dict[str, _Template] = {
    "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION": _unconfirmed_records,
    "STATUS_PERIOD_NARROW_MARGIN": lambda p: (
        "Your proposed application date is within a week of the earliest the holding "
        f"period allows ({format_date(p.get('earliest_application_date'))}), and the "
        "date an application is received is not entirely in your control."
    ),
    "CONFLICTING_SOURCE_DATES": lambda p: (
        "The dates on this trip conflict between sources, so it is not counted as confirmed."
    ),
    "OVERLAPPING_TRAVEL": lambda p: (
        "These trips cover overlapping days. Overlapping days are counted once, not "
        "twice, but one of the records is likely wrong."
    ),
    "UNCERTAIN_TRAVEL_DATE": lambda p: (
        "The dates on this trip are marked estimated or unknown, so it does not count "
        "towards your confirmed totals."
    ),
    "NEAR_STANDARD_THRESHOLD": lambda p: (
        "This trip covers "
        f"{format_date(p.get('physical_presence_date'))}, the first day of your "
        "qualifying period — the single day presence is tested on."
    ),
    "TRAVEL_OUTSIDE_WINDOW": lambda p: (
        "This trip falls entirely outside your qualifying period, so it does not "
        "affect any total. It is kept for your records."
    ),
}


# --- next-action codes ------------------------------------------------------

NEXT_ACTION_TEMPLATES: dict[str, _Template] = {
    "SELECT_APPLICATION_DATE": lambda p: (
        "Consider moving your proposed application date to "
        f"{format_date(p.get('resolving_application_date'))}."
        if p.get("resolving_application_date")
        else "Consider moving your proposed application date to "
        f"{format_date(p.get('earliest_application_date'))} or later."
    ),
}


# --- stale reason codes -----------------------------------------------------

STALE_REASON_TEMPLATES: dict[str, _Template] = {
    "APPLICATION_DATE_CHANGED": lambda p: (
        "Your proposed application date changed after this was worked out."
    ),
    "TRAVEL_RECORD_CHANGED": lambda p: "Your travel records changed after this was worked out.",
}


# --- rendering --------------------------------------------------------------


def _render(
    registry: dict[str, _Template], code: str | None, parameters: Parameters | None
) -> str | None:
    if code is None:
        return None
    template = registry.get(code)
    if template is None:
        return None
    return template(parameters or {})


def render_summary(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(SUMMARY_TEMPLATES, code, parameters)


def render_limitation(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(LIMITATION_TEMPLATES, code, parameters)


def render_next_action(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(NEXT_ACTION_TEMPLATES, code, parameters)


def render_stale_reason(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(STALE_REASON_TEMPLATES, code, parameters)
