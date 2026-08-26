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

from app.requirements.rules_core import PRESENCE_SEARCH_HORIZON_DAYS

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


def _unevidenced_clause(count: int | None) -> str:
    """ "One confirmed trip has …" / "Four confirmed trips have …".

    A missing count degrades to "Some", which is vague but never wrong — the same
    discipline the absence summaries use when a figure is absent.
    """
    if count == 1:
        return "One confirmed trip has no document attached"
    return f"{count if count is not None else 'Some'} confirmed trips have no document attached"


# --- summary codes ----------------------------------------------------------


def _absence_summary(
    p: Parameters,
    *,
    period: str,
    verdict: str,
    verdict_covers_unconfirmed: bool = False,
) -> str:
    """Shared body for the ten total/final-year band codes.

    `days` is always the trusted total; `provisional_days` includes records that have not
    been confirmed. The confirmed figure always leads and is always named as confirmed.

    **Where the verdict attaches matters.** The verdict clause comes from the result's
    summary code, and under the §6.2 sensitivity rule that code can be the *provisional*
    band's — trusted 400 days bands as SUPPORTED while provisional 440 bands as
    NEAR_THRESHOLD, and no cap applies. Appending "that is close to the standard
    threshold" straight after "400 days … from confirmed travel records" would attach a
    verdict about 440 to the figure 400. So when the two diverge, the verdict follows the
    provisional figure instead. `verdict_covers_unconfirmed` marks the two capped codes
    whose wording already speaks about both figures.
    """
    confirmed = _int(p, "days")
    threshold = _int(p, "threshold")
    provisional = _int(p, "provisional_days")

    # No figure means nothing for a threshold verdict to describe. Degrade to a statement
    # of the gap rather than asserting an outcome with no number behind it.
    if confirmed is None:
        return f"The number of days outside the UK {period} is not available on this result."

    sentence = f"{_days(confirmed)} outside the UK {period}, from confirmed travel records"
    if threshold is not None:
        sentence += f", against a threshold of {threshold}"
    sentence += "."

    if provisional is not None and provisional > confirmed:
        extra = provisional - confirmed
        sentence += (
            f" Records you have not confirmed would add {_days(extra)},"
            f" bringing the total to {provisional}."
        )
        if verdict_covers_unconfirmed:
            sentence += f" {verdict}"
        else:
            sentence += f" Including those, {verdict[0].lower()}{verdict[1:]}"
    else:
        sentence += f" {verdict}"
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
            else (
                f" No later date within the next {PRESENCE_SEARCH_HORIZON_DAYS} days"
                " clears that day."
            )
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
        verdict_covers_unconfirmed=True,
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
        verdict_covers_unconfirmed=True,
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
    # Says the records are consistent *first*. The unevidenced trips are a separate,
    # weaker fact, and leading with them would read as though something were wrong with
    # the travel history — which is precisely what this rule has just found is not so.
    # Branches on the count because the canonical demo case has exactly one such trip, and
    # "Some confirmed trips" for a single Greece booking is a small lie in the one sentence
    # the requirement card leads with.
    "TRAVEL_RECORDS_UNEVIDENCED": lambda p: (
        "Your travel records are internally consistent. "
        + _unevidenced_clause(_int(p, "unevidenced_count"))
        + ", which does not affect any total."
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
    # "no document attached", not "no evidence" — the user attaches documents, and
    # "evidence" invites them to think something has judged what they attached. Nothing
    # has: attaching is their assertion, and no rule reads the document (ADR-0021).
    #
    # It also does not tell them to attach one. A trip with no booking is not a defect —
    # people take trips they have no paperwork for — so this states the fact and leaves
    # the decision with them.
    "MISSING_TRAVEL_EVIDENCE": lambda p: (
        "No document is attached to this trip. That does not affect your absence "
        "totals, which are worked out from the dates you entered."
    ),
    "TRAVEL_OUTSIDE_WINDOW": lambda p: (
        "This trip falls entirely outside your qualifying period, so it does not "
        "affect any total. It is kept for your records."
    ),
    "LEAP_DAY_BOUNDARY_ASSUMPTION": lambda p: (
        "Your application date is 29 February. Guidance does not say how the five-year "
        "period is counted back from a leap day, so we count back to 28 February and "
        "start your qualifying period on "
        f"{format_date(p.get('qualifying_period_start'))}. "
        "This moves the day your presence is tested by one day."
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
    # No reachable writer yet: a confirmed route profile cannot be edited on an active case
    # (`confirm_route_profile` requires a draft). The reason code and this sentence exist so
    # that the invalidation service handles the kind its declarations already name, rather
    # than the profile-edit path arriving later and having to remember to add both.
    "ROUTE_PROFILE_CHANGED": lambda p: (
        "Your immigration status details changed after this was worked out."
    ),
    # "documents you attached", not "your evidence": the user attached them, and the
    # sentence has to work whether they added one, removed one, or deleted the file.
    "EVIDENCE_SUPPORT_CHANGED": lambda p: (
        "The documents attached to your travel records changed after this was worked out."
    ),
    # Says the rules changed, and stops there. It deliberately does not say "your result
    # may change" — nobody has rechecked it yet, so that would be a guess, and a guess
    # about eligibility is the one thing this product does not make.
    "RULE_VERSION_CHANGED": lambda p: (
        "We updated how this requirement is checked, so this needs working out again."
    ),
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


#: `Issue.title_code` → the queue's heading and body for that issue (Domain §36, UI/UX §10).
#:
#: UI/UX §10 governs the register: calm, specific, non-alarmist. No "Something went wrong",
#: no urgency the situation does not carry, and — for a stale issue especially — nothing
#: implying the preserved conclusion still holds. The same trap `StaleAssessmentNotice`
#: names on the frontend: a stale conclusion has *not* been rechecked, so it may not be
#: described as standing, holding, or still valid.
ISSUE_TITLE_TEMPLATES: dict[str, _Template] = {
    "ISSUE_STALE_ASSESSMENT": lambda p: f"Recheck {p.get('requirement_title', 'this requirement')}",
    "ISSUE_NEAR_THRESHOLD_ABSENCES": lambda p: (
        f"{p.get('requirement_title', 'This requirement')} is close to its threshold"
    ),
    "ISSUE_NEAR_THRESHOLD_STATUS_PERIOD": lambda p: (
        "Your application date is close to the earliest one that qualifies"
    ),
    "ISSUE_UNSUPPORTED_COMPLEXITY": lambda p: (
        f"{p.get('requirement_title', 'This requirement')} needs further review"
    ),
    "ISSUE_OVERLAPPING_TRAVEL": lambda p: (
        f"Your trip to {p.get('destination', 'this destination')} overlaps another trip"
    ),
    "ISSUE_UNCERTAIN_TRAVEL_DATE": lambda p: (
        f"Confirm the dates of your trip to {p.get('destination', 'this destination')}"
    ),
    "ISSUE_UNCERTAIN_DATE_OUTSIDE": lambda p: (
        f"Your trip to {p.get('destination', 'this destination')} has uncertain dates"
    ),
    # Names the trip and stops. Not "Attach a document to ..." — a title in the
    # imperative reads as an instruction, and the product does not know that this user
    # has a document for this trip, or that they need one.
    "ISSUE_MISSING_TRAVEL_EVIDENCE": lambda p: (
        f"No document attached to your trip to {p.get('destination', 'this destination')}"
    ),
    "ISSUE_RECALCULATION_FAILED": lambda p: "We could not recheck your conclusions",
}

ISSUE_BODY_TEMPLATES: dict[str, _Template] = {
    "ISSUE_STALE_ASSESSMENT": lambda p: (
        "An input behind this conclusion changed, so it has not been rechecked. "
        "The conclusion shown is the one reached before that change."
    ),
    "ISSUE_NEAR_THRESHOLD_ABSENCES": lambda p: (
        "The number of days behind this conclusion sits close to the threshold it is "
        "measured against. Small changes to your travel records could move it across."
    ),
    "ISSUE_NEAR_THRESHOLD_STATUS_PERIOD": lambda p: (
        "You will have held your settled status free of time restrictions for just over "
        "the required 12 months on your proposed application date."
    ),
    # UI/UX §10.2, close to verbatim. The point of the wording is that stopping is a
    # deliberate outcome, not a breakdown: the product says what it will not do and why.
    "ISSUE_UNSUPPORTED_COMPLEXITY": lambda p: (
        "This part of your case falls in a range the prototype cannot assess reliably. "
        "We have paused this assessment rather than reaching an uncertain conclusion."
    ),
    "ISSUE_OVERLAPPING_TRAVEL": lambda p: (
        "Two of your trips cover some of the same dates. Overlapping records make the "
        "days outside the UK ambiguous."
    ),
    "ISSUE_UNCERTAIN_TRAVEL_DATE": lambda p: (
        "These dates are recorded as uncertain, so they are not counted in the confirmed totals."
    ),
    "ISSUE_UNCERTAIN_DATE_OUTSIDE": lambda p: (
        "These dates are recorded as uncertain. This trip falls outside your qualifying "
        "period, so it does not affect any figure."
    ),
    # No "something went wrong", no apology, and above all no suggestion that the figures
    # on screen are fine. The one thing this sentence must establish is that the numbers
    # the user is looking at did not move — the failure changed nothing, which is both
    # reassuring about the data and *not* reassuring about the conclusions.
    # Two jobs, in this order: say the totals are unaffected, then say what a document
    # would be *for*. Getting that backwards would imply the figures are provisional
    # until documents arrive, which is false — they are worked out from the dates the
    # user entered, and nothing here has read any document (ADR-0021).
    "ISSUE_MISSING_TRAVEL_EVIDENCE": lambda p: (
        "Your absence totals are worked out from the dates you entered, so this does not "
        "change any figure. A booking or ticket is the kind of thing that supports a trip "
        "if you are asked about it later."
    ),
    "ISSUE_RECALCULATION_FAILED": lambda p: (
        "The last attempt to recheck your conclusions did not finish. Nothing was changed: "
        "the figures on your case are still the ones worked out before your last edit."
    ),
}

#: Why the user should care — the "why it matters" line of Domain §44.5. States the
#: consequence, never a prediction and never advice.
ISSUE_IMPACT_TEMPLATES: dict[str, _Template] = {
    "ISSUE_STALE_ASSESSMENT": lambda p: (
        "Until it is rechecked, this conclusion may no longer match your case data."
    ),
    # States the sensitivity, never the outcome. "You may be refused" is a prediction this
    # product does not make (CLAUDE.md §1); "a few days either way changes the band" is a
    # property of the calculation the user can check.
    "ISSUE_NEAR_THRESHOLD_ABSENCES": lambda p: (
        "A small correction to your travel records could change which band this falls in."
    ),
    # Names the inputs that actually move this figure. Travel records cannot: the holding
    # period reads the grant date and the application date, and has no bands.
    "ISSUE_NEAR_THRESHOLD_STATUS_PERIOD": lambda p: (
        "A correction to your grant date, or an earlier application date, could put this "
        "below the required period."
    ),
    "ISSUE_UNSUPPORTED_COMPLEXITY": lambda p: (
        "This requirement has no conclusion from us. It needs a person who can advise on "
        "your circumstances."
    ),
    "ISSUE_OVERLAPPING_TRAVEL": lambda p: (
        "While the records overlap, the total days outside the UK cannot be relied on."
    ),
    "ISSUE_UNCERTAIN_TRAVEL_DATE": lambda p: (
        "Your confirmed totals exclude these days, so they read lower than your full history."
    ),
    "ISSUE_UNCERTAIN_DATE_OUTSIDE": lambda p: (
        "No figure changes either way. You can set this aside."
    ),
    # Says plainly that setting it aside is fine, like the out-of-window uncertain date.
    # Anything stronger would be advice about what the Home Office will ask for, which
    # this product does not give (CLAUDE.md §1).
    "ISSUE_MISSING_TRAVEL_EVIDENCE": lambda p: (
        "Nothing in your assessment depends on this. You can attach a document or set this aside."
    ),
    # Points at the same consequence a stale conclusion has, because that is exactly the
    # state the case is left in — the failure is why it is still in it.
    "ISSUE_RECALCULATION_FAILED": lambda p: (
        "Any conclusion awaiting a recheck stays out of date until one succeeds."
    ),
}


def render_issue_title(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(ISSUE_TITLE_TEMPLATES, code, parameters)


def render_issue_body(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(ISSUE_BODY_TEMPLATES, code, parameters)


def render_issue_impact(code: str | None, parameters: Parameters | None = None) -> str | None:
    return _render(ISSUE_IMPACT_TEMPLATES, code, parameters)
