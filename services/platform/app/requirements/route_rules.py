"""The three route-scope rules (RULES_SPEC §7.1, §7.2, §7.2b).

Each evaluator is a **pure function** — no I/O, no clock reads, no randomness — so
the same inputs always give the same outcome. The reference date the adult rule
needs is passed in by the caller (the service reads the clock, never the rule).

`route.standard_section_6_1` is the composite guard and the only rule that depends
on other rules' *conclusions* rather than raw inputs; here that dependency is plain
function composition — the caller evaluates the two upstream rules and passes their
outcomes in. At M3B the composite persists as an `AssessmentResult` linking the route
profile it reads directly, but its dependence on the adult/status *conclusions* is NOT
yet a persisted invalidation edge (§25.1's input kinds have no result kind). That edge —
so an application-date change that restales `route.adult_applicant` also restales the
composite — is owned by selective invalidation (M6, ADR-0007 consequences).

Status is taken as a raw string (not the applicants `StatusType` enum) so this
module depends on nothing outside `requirements`; the values mirror RFC §9.2.
"""

from dataclasses import dataclass
from datetime import date

from app.requirements.domain import RULE_SET, SEMANTIC_VERSION, Conclusion

# Requirement keys — stable public identifiers (RULES_SPEC §7). Never rename once
# assessments reference them.
KEY_ADULT = "route.adult_applicant"
KEY_STATUS = "route.supported_status"
KEY_STANDARD = "route.standard_section_6_1"

# Summary codes (RULES_SPEC §7). A code is None only for NOT_YET_ASSESSED, which the
# spec gives no code for; complete data (as required at confirm) never yields None.
ROUTE_ADULT_CONFIRMED = "ROUTE_ADULT_CONFIRMED"
ROUTE_APPLICANT_UNDER_18 = "ROUTE_APPLICANT_UNDER_18"
STATUS_TYPE_SUPPORTED = "STATUS_TYPE_SUPPORTED"
STATUS_TYPE_UNSUPPORTED = "STATUS_TYPE_UNSUPPORTED"
ROUTE_STANDARD_CONFIRMED = "ROUTE_STANDARD_CONFIRMED"
ROUTE_SPOUSE_UNSUPPORTED = "ROUTE_SPOUSE_UNSUPPORTED"
ROUTE_MAY_BE_BRITISH = "ROUTE_MAY_BE_BRITISH"
ROUTE_PREREQUISITES_UNMET = "ROUTE_PREREQUISITES_UNMET"

# Status types that satisfy route.supported_status (RULES_SPEC §7.2; RFC §9.2).
_SUPPORTED_STATUS = frozenset({"ILR", "ILE", "EU_SETTLED_STATUS"})


@dataclass(frozen=True)
class RuleOutcome:
    requirement_key: str
    conclusion: Conclusion
    summary_code: str | None


def age_in_years(dob: date, on: date) -> int:
    """Completed years from `dob` to `on`. A birthday counts on the day it lands;
    a 29 Feb birthday completes on 1 Mar in a non-leap year (conventional handling)."""
    had_birthday = (on.month, on.day) >= (dob.month, dob.day)
    return on.year - dob.year - (0 if had_birthday else 1)


def evaluate_adult(dob: date | None, *, reference_date: date) -> RuleOutcome:
    """§7.1. Adult (18+) on the application date. At M2 the reference date is today
    (no proposed application date exists until M3A)."""
    if dob is None:
        return RuleOutcome(KEY_ADULT, Conclusion.NOT_YET_ASSESSED, None)
    if age_in_years(dob, reference_date) >= 18:
        return RuleOutcome(KEY_ADULT, Conclusion.SUPPORTED, ROUTE_ADULT_CONFIRMED)
    # Under 18 is the registration route, not naturalisation — unsupported here.
    return RuleOutcome(KEY_ADULT, Conclusion.NOT_CURRENTLY_SATISFIED, ROUTE_APPLICANT_UNDER_18)


def evaluate_supported_status(status_type: str | None) -> RuleOutcome:
    """§7.2. ILR / ILE / EUSS satisfy lawful-residence and time-restriction freedom."""
    if status_type is None or status_type == "UNKNOWN":
        return RuleOutcome(KEY_STATUS, Conclusion.NOT_YET_ASSESSED, None)
    if status_type in _SUPPORTED_STATUS:
        return RuleOutcome(KEY_STATUS, Conclusion.SUPPORTED, STATUS_TYPE_SUPPORTED)
    # OTHER (incl. pre-settled, WA permanent residence): unsupported, needs a human.
    return RuleOutcome(
        KEY_STATUS, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, STATUS_TYPE_UNSUPPORTED
    )


def evaluate_standard_section_6_1(
    *,
    married_to_british_citizen: bool | None,
    may_already_be_british: bool | None,
    adult: RuleOutcome,
    status: RuleOutcome,
    profile_confirmed: bool,
) -> RuleOutcome:
    """§7.2b. Composite guard: the case fits the one supported route, or it doesn't.

    Precedence (approved M2 plan): unconfirmed → not-yet-assessed; spouse route →
    professional review; may-be-British → requires judgement; failed prerequisites
    → not currently satisfied; otherwise supported."""
    if not profile_confirmed:
        return RuleOutcome(KEY_STANDARD, Conclusion.NOT_YET_ASSESSED, None)
    if married_to_british_citizen:
        return RuleOutcome(
            KEY_STANDARD, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED, ROUTE_SPOUSE_UNSUPPORTED
        )
    if may_already_be_british:
        return RuleOutcome(KEY_STANDARD, Conclusion.REQUIRES_JUDGEMENT, ROUTE_MAY_BE_BRITISH)
    prerequisites_met = (
        adult.conclusion is Conclusion.SUPPORTED and status.conclusion is Conclusion.SUPPORTED
    )
    if not prerequisites_met:
        return RuleOutcome(
            KEY_STANDARD, Conclusion.NOT_CURRENTLY_SATISFIED, ROUTE_PREREQUISITES_UNMET
        )
    return RuleOutcome(KEY_STANDARD, Conclusion.SUPPORTED, ROUTE_STANDARD_CONFIRMED)


@dataclass(frozen=True)
class RouteSupportDecision:
    """The full route-support evaluation: the composite plus its two upstream
    outcomes, carried together so the decision can be explained and reproduced."""

    composite: RuleOutcome
    adult: RuleOutcome
    status: RuleOutcome
    rule_set: str = RULE_SET
    semantic_version: str = SEMANTIC_VERSION

    @property
    def outcomes(self) -> tuple[RuleOutcome, ...]:
        return (self.adult, self.status, self.composite)


def evaluate_route_support(
    *,
    date_of_birth: date | None,
    status_type: str | None,
    married_to_british_citizen: bool | None,
    may_already_be_british: bool | None,
    reference_date: date,
    profile_confirmed: bool,
) -> RouteSupportDecision:
    """Evaluate all three route rules and compose the standard-route guard."""
    adult = evaluate_adult(date_of_birth, reference_date=reference_date)
    status = evaluate_supported_status(status_type)
    composite = evaluate_standard_section_6_1(
        married_to_british_citizen=married_to_british_citizen,
        may_already_be_british=may_already_be_british,
        adult=adult,
        status=status,
        profile_confirmed=profile_confirmed,
    )
    return RouteSupportDecision(composite=composite, adult=adult, status=status)
