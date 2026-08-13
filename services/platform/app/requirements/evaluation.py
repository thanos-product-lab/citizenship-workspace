"""The evaluation contract and the route-scope evaluator.

An evaluator is a **pure function of primitive inputs → `EvaluatedResult`s**. It reads
no ORM objects and touches no I/O — the assessment service gathers the current versioned
inputs, flattens them to primitives plus their version ids, and hands them here. Keeping
this module free of SQLAlchemy and of other modules' domain types is what lets the rules
stay reproducible and independently testable (as `route_rules` already is).

`route_rules` remains the single *evaluator* for route support; this module only shapes
its outcomes into persisted-result records and declares the exact input links each result
read. The assessment layer is the single *result store* (ADR-0007): it consumes these
records and writes `AssessmentResult` rows — nothing else records a route conclusion.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from app.requirements.domain import Conclusion
from app.requirements.route_rules import (
    KEY_ADULT,
    KEY_STANDARD,
    KEY_STATUS,
    evaluate_route_support,
)
from app.requirements.rules_core import (
    FINAL_YEAR_ABSENCE_THRESHOLD_DAYS,
    STATUS_HOLDING_NARROW_MARGIN_DAYS,
    TOTAL_ABSENCE_THRESHOLD_DAYS,
    Band,
    Window,
    absence_union,
    absent_dates,
    add_years,
    band_final_year_absences,
    band_total_absences,
    count_in_window,
    final_year_window,
    more_severe,
    physical_presence_date,
    qualifying_window,
    resolve_presence_date,
)

# The holding-period requirement key (ROUTE_AND_STATUS group, but its own rule).
KEY_STATUS_HOLDING = "status.holding_period"

# Residence requirement keys whose evaluators exist.
KEY_QUALIFYING_PERIOD = "residence.qualifying_period"
KEY_PHYSICAL_PRESENCE = "residence.physical_presence_start_date"
KEY_TOTAL_ABSENCES = "residence.total_absences"
KEY_FINAL_YEAR_ABSENCES = "residence.final_year_absences"
KEY_TRAVEL_CONSISTENCY = "residence.travel_consistency"

# Requirement keys whose evaluators exist. GET /requirements reports every catalogued
# requirement; those not in this set have no trusted result yet and read as
# NOT_YET_ASSESSED. knowledge/referee/character keys join as their evaluators land.
ROUTE_REQUIREMENT_KEYS: tuple[str, ...] = (KEY_ADULT, KEY_STATUS, KEY_STANDARD)
STATUS_REQUIREMENT_KEYS: tuple[str, ...] = (KEY_STATUS_HOLDING,)
RESIDENCE_REQUIREMENT_KEYS: tuple[str, ...] = (
    KEY_QUALIFYING_PERIOD,
    KEY_PHYSICAL_PRESENCE,
    KEY_TOTAL_ABSENCES,
    KEY_FINAL_YEAR_ABSENCES,
    KEY_TRAVEL_CONSISTENCY,
)
IN_SCOPE_REQUIREMENT_KEYS: frozenset[str] = frozenset(
    ROUTE_REQUIREMENT_KEYS + STATUS_REQUIREMENT_KEYS + RESIDENCE_REQUIREMENT_KEYS
)


class LinkInputKind(StrEnum):
    """The versioned-input kinds an `AssessmentInputLink` can point at (Domain §31.1).
    Distinct from a rule's *dependency* kind (`DependencyInputKind`): a dependency names
    an input class (ROUTE_PROFILE); a link names the concrete version read
    (ROUTE_PROFILE_VERSION)."""

    ROUTE_PROFILE_VERSION = "ROUTE_PROFILE_VERSION"
    APPLICATION_DATE_VERSION = "APPLICATION_DATE_VERSION"
    TRAVEL_RECORD_VERSION = "TRAVEL_RECORD_VERSION"


class ContributionRole(StrEnum):
    REQUIRED = "REQUIRED"
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    LIMITING = "LIMITING"
    CONTEXTUAL = "CONTEXTUAL"


class LimitationSeverity(StrEnum):
    INFORMATION = "INFORMATION"
    CAUTION = "CAUTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKING = "BLOCKING"


@dataclass(frozen=True)
class Limitation:
    """A structured condition reducing confidence in a result (Domain §33). Code + severity
    + parameters, never prose; `affected_input_ids` names the versions responsible."""

    code: str
    severity: LimitationSeverity
    message_parameters: dict[str, object] = field(default_factory=dict)
    affected_input_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message_parameters": self.message_parameters,
            "affected_input_ids": list(self.affected_input_ids),
        }


@dataclass(frozen=True)
class NextAction:
    """A structured action that would move a result forward (Domain §34)."""

    code: str
    label_parameters: dict[str, object] = field(default_factory=dict)
    priority: int = 0
    blocking: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "label_parameters": self.label_parameters,
            "priority": self.priority,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class InputLinkSpec:
    """One versioned input a result actually read, to be persisted as an
    `AssessmentInputLink`. The set of these per result must equal the rule's declared
    dependencies (strict provenance): reading an undeclared input, or declaring one the
    evaluator never reads, is a defect the provenance test catches."""

    input_kind: LinkInputKind
    input_version_id: uuid.UUID
    input_key: str | None = None
    contribution_role: ContributionRole = ContributionRole.REQUIRED


@dataclass(frozen=True)
class EvaluatedResult:
    requirement_key: str
    conclusion: str
    summary_code: str | None
    summary_parameters: dict[str, object] = field(default_factory=dict)
    calculation_breakdown: dict[str, object] = field(default_factory=dict)
    input_links: tuple[InputLinkSpec, ...] = ()
    limitations: tuple[Limitation, ...] = ()
    next_actions: tuple[NextAction, ...] = ()


@dataclass(frozen=True)
class RouteAssessmentInputs:
    """The flattened, primitive inputs the route-scope rules read, plus the ids of the
    versions they came from so the results can link exact provenance. The application
    date is the reference date the age check is evaluated at — a trusted run has one
    (recalculation requires a selected date), so it is not optional here."""

    date_of_birth: date | None
    status_type: str | None
    status_granted_on: date | None
    married_to_british_citizen: bool | None
    may_already_be_british: bool | None
    application_date: date
    route_profile_version_id: uuid.UUID
    application_date_version_id: uuid.UUID
    profile_confirmed: bool = True


def evaluate_route_requirements(inputs: RouteAssessmentInputs) -> list[EvaluatedResult]:
    """Evaluate the three route-scope rules and shape them into result records with exact
    input links. The age check uses the selected application date as its reference (not
    the wall clock), so the persisted result is anchored to a versioned input."""
    decision = evaluate_route_support(
        date_of_birth=inputs.date_of_birth,
        status_type=inputs.status_type,
        married_to_british_citizen=inputs.married_to_british_citizen,
        may_already_be_british=inputs.may_already_be_british,
        reference_date=inputs.application_date,
        profile_confirmed=inputs.profile_confirmed,
    )

    profile_link = InputLinkSpec(
        LinkInputKind.ROUTE_PROFILE_VERSION, inputs.route_profile_version_id
    )
    date_link = InputLinkSpec(
        LinkInputKind.APPLICATION_DATE_VERSION, inputs.application_date_version_id
    )
    reference: dict[str, object] = {"reference_date": inputs.application_date.isoformat()}

    # Per-result links mirror the seeded dependency rows (0007): adult reads DOB + the
    # application date; supported_status reads the status type; the composite reads the
    # profile answers, and its dependence on the adult/status conclusions is composition,
    # not an input link.
    return [
        EvaluatedResult(
            requirement_key=KEY_ADULT,
            conclusion=decision.adult.conclusion.value,
            summary_code=decision.adult.summary_code,
            summary_parameters=reference,
            input_links=(
                InputLinkSpec(
                    LinkInputKind.ROUTE_PROFILE_VERSION,
                    inputs.route_profile_version_id,
                    input_key="date_of_birth",
                ),
                date_link,
            ),
        ),
        EvaluatedResult(
            requirement_key=KEY_STATUS,
            conclusion=decision.status.conclusion.value,
            summary_code=decision.status.summary_code,
            input_links=(
                InputLinkSpec(
                    LinkInputKind.ROUTE_PROFILE_VERSION,
                    inputs.route_profile_version_id,
                    input_key="status_type",
                ),
            ),
        ),
        # The composite reads the profile answers directly (one input link), and composes
        # the adult/status *conclusions* — a result→result dependency §25.1 has no input
        # kind for. Those upstream conclusions are recorded as snapshots for explanation
        # only; the structural edge that must restale the composite when an upstream
        # restales is owned by selective invalidation (M6). Until then a change reaching
        # the composite re-runs the whole route set, so it stays correct — just not
        # selectively. Do NOT add an APPLICATION_DATE link here: the composite does not
        # read the date, and links must name only inputs actually read.
        EvaluatedResult(
            requirement_key=KEY_STANDARD,
            conclusion=decision.composite.conclusion.value,
            summary_code=decision.composite.summary_code,
            summary_parameters={
                "adult_conclusion": decision.adult.conclusion.value,
                "status_conclusion": decision.status.conclusion.value,
            },
            input_links=(profile_link,),
        ),
    ]


def evaluate_status_holding_period(inputs: RouteAssessmentInputs) -> EvaluatedResult:
    """§7.3. Free from immigration time restrictions for the 12 months before applying:
    earliest application date = status granted + 1 year. A 7-day caution band sits above it
    (guidance is not to-the-day and the received date is not fully controllable)."""
    links = (
        InputLinkSpec(
            LinkInputKind.ROUTE_PROFILE_VERSION,
            inputs.route_profile_version_id,
            input_key="status_granted_on",
        ),
        InputLinkSpec(LinkInputKind.APPLICATION_DATE_VERSION, inputs.application_date_version_id),
    )
    if inputs.status_granted_on is None:
        return EvaluatedResult(
            KEY_STATUS_HOLDING, Conclusion.INCOMPLETE.value, None, input_links=links
        )

    earliest = add_years(inputs.status_granted_on, 1)
    params: dict[str, object] = {"earliest_application_date": earliest.isoformat()}
    narrow_until = earliest + timedelta(days=STATUS_HOLDING_NARROW_MARGIN_DAYS)

    if inputs.application_date >= narrow_until:
        return EvaluatedResult(
            KEY_STATUS_HOLDING,
            Conclusion.SUPPORTED.value,
            "STATUS_PERIOD_SATISFIED",
            summary_parameters=params,
            input_links=links,
        )
    if inputs.application_date >= earliest:
        limitation = Limitation(
            code="STATUS_PERIOD_NARROW_MARGIN",
            severity=LimitationSeverity.CAUTION,
            message_parameters=dict(params),
        )
        return EvaluatedResult(
            KEY_STATUS_HOLDING,
            Conclusion.SUPPORTED.value,
            "STATUS_PERIOD_NARROW_MARGIN",
            summary_parameters=params,
            input_links=links,
            limitations=(limitation,),
        )
    # Applied before the holding period is met — return the earliest date as a next action.
    return EvaluatedResult(
        KEY_STATUS_HOLDING,
        Conclusion.NOT_CURRENTLY_SATISFIED.value,
        "STATUS_PERIOD_NOT_YET_MET",
        summary_parameters=params,
        input_links=links,
        next_actions=(
            NextAction(
                code="SELECT_APPLICATION_DATE",
                label_parameters=dict(params),
                priority=1,
                blocking=True,
            ),
        ),
    )


# --- residence evaluators (RULES_SPEC §7.4-7.8) -----------------------------

_SATISFIED_OR_NEAR = frozenset({Conclusion.SUPPORTED, Conclusion.NEAR_THRESHOLD})
_UNCONFIRMED_LIMITATION = "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION"
_UNCERTAIN_CONFIDENCES = frozenset({"ESTIMATED", "UNKNOWN"})


@dataclass(frozen=True)
class TripInput:
    """One active travel record, flattened. `is_trusted` is the §6.1 gate — ACTIVE and
    CONFIRMED and EXACT — decided by the service; the evaluator never re-derives trust.
    `date_confidence` is carried raw for the data-quality (travel-consistency) rule."""

    departure_date: date
    return_date: date
    travel_record_version_id: uuid.UUID
    is_trusted: bool
    date_confidence: str = "EXACT"


@dataclass(frozen=True)
class ResidenceAssessmentInputs:
    application_date: date
    application_date_version_id: uuid.UUID
    trips: tuple[TripInput, ...]


def _app_date_link(inputs: ResidenceAssessmentInputs) -> InputLinkSpec:
    return InputLinkSpec(LinkInputKind.APPLICATION_DATE_VERSION, inputs.application_date_version_id)


def _travel_links(trips: tuple[TripInput, ...]) -> tuple[InputLinkSpec, ...]:
    # Every active travel record the rule read is linked (the ALL_ACTIVE_TRAVEL_RECORDS
    # dependency), trusted or not — the rule reads all of them to compute both totals.
    return tuple(
        InputLinkSpec(
            LinkInputKind.TRAVEL_RECORD_VERSION,
            trip.travel_record_version_id,
            contribution_role=ContributionRole.CONTEXTUAL,
        )
        for trip in trips
    )


def _spans(trips: Iterable[TripInput]) -> list[tuple[date, date]]:
    return [(trip.departure_date, trip.return_date) for trip in trips]


def _uncertain_ids(trips: tuple[TripInput, ...]) -> tuple[str, ...]:
    return tuple(str(t.travel_record_version_id) for t in trips if not t.is_trusted)


def _threshold_conclusion(
    trusted_total: int,
    provisional_total: int,
    band_fn: Callable[[int], Band],
    capped_summary_code: str,
    uncertain_ids: tuple[str, ...],
) -> tuple[Conclusion, str, tuple[Limitation, ...]]:
    """Band the trusted total, then apply the §6.2 sensitivity rule: if the trusted total is
    satisfied/near but the provisional total (uncertain records included) would band worse,
    downgrade to that band capped at INCOMPLETE and attach a REVIEW_REQUIRED limitation.
    The conclusion is never upgraded by provisional data (provisional_total >= trusted_total).

    When the downgrade is *capped* to INCOMPLETE, the summary code is the sensitivity-specific
    `capped_summary_code`, never the provisional band's failure code — otherwise an INCOMPLETE
    conclusion would carry an "...EXCEEDED" headline that overstates unconfirmed data (§6.2)."""
    trusted_band = band_fn(trusted_total)
    if trusted_band.conclusion in _SATISFIED_OR_NEAR:
        provisional_band = band_fn(provisional_total)
        if more_severe(provisional_band.conclusion, trusted_band.conclusion):
            downgraded = provisional_band.conclusion
            summary_code = provisional_band.summary_code
            if more_severe(downgraded, Conclusion.INCOMPLETE):
                downgraded = Conclusion.INCOMPLETE
                summary_code = capped_summary_code
            limitation = Limitation(
                code=_UNCONFIRMED_LIMITATION,
                severity=LimitationSeverity.REVIEW_REQUIRED,
                message_parameters={
                    "trusted_days": trusted_total,
                    "provisional_days": provisional_total,
                },
                affected_input_ids=uncertain_ids,
            )
            return downgraded, summary_code, (limitation,)
    return trusted_band.conclusion, trusted_band.summary_code, ()


def _evaluate_qualifying_period(inputs: ResidenceAssessmentInputs) -> EvaluatedResult:
    """§7.4. A calculation, not a test — always SUPPORTED once an application date exists.
    Owns the window breakdown every other residence rule cites."""
    q = qualifying_window(inputs.application_date)
    fy = final_year_window(inputs.application_date)
    breakdown: dict[str, object] = {
        "application_date": inputs.application_date.isoformat(),
        "qualifying_period_start": q.start.isoformat(),
        "qualifying_period_end": q.end.isoformat(),
        "final_year_start": fy.start.isoformat(),
        "final_year_end": fy.end.isoformat(),
        "physical_presence_date": q.start.isoformat(),
        "derivation": "application_date - 5 years + 1 day",
    }
    return EvaluatedResult(
        requirement_key=KEY_QUALIFYING_PERIOD,
        conclusion=Conclusion.SUPPORTED.value,
        summary_code="QUALIFYING_PERIOD_DERIVED",
        calculation_breakdown=breakdown,
        input_links=(_app_date_link(inputs),),
    )


def _evaluate_physical_presence(inputs: ResidenceAssessmentInputs) -> EvaluatedResult:
    """§7.5. Present on the anchor unless a trip's absent set contains it. Confirmed absence
    → NOT_CURRENTLY_SATISFIED with the nearest resolving date; uncertain-only absence →
    INCOMPLETE (the §6.2 gate applied to a membership test, not a total)."""
    anchor = physical_presence_date(inputs.application_date)
    trusted_union = absence_union(_spans(t for t in inputs.trips if t.is_trusted))
    provisional_union = absence_union(_spans(inputs.trips))
    links = (_app_date_link(inputs), *_travel_links(inputs.trips))
    params: dict[str, object] = {"physical_presence_date": anchor.isoformat()}

    if anchor in trusted_union:
        # The resolving date is searched over the *trusted* absent union only: an unconfirmed
        # trip must never shape the suggested date. So the offered date clears confirmed
        # absence — if an uncertain trip also covers it, presence there reads INCOMPLETE until
        # that record is confirmed. Correct trade-off (§6.2): unconfirmed data cannot drive it.
        resolving = resolve_presence_date(trusted_union, inputs.application_date)
        next_actions: tuple[NextAction, ...] = ()
        if resolving is not None:
            params["resolving_application_date"] = resolving.isoformat()
            next_actions = (
                NextAction(
                    code="SELECT_APPLICATION_DATE",
                    label_parameters={"resolving_application_date": resolving.isoformat()},
                    priority=1,
                    blocking=True,
                ),
            )
        return EvaluatedResult(
            requirement_key=KEY_PHYSICAL_PRESENCE,
            conclusion=Conclusion.NOT_CURRENTLY_SATISFIED.value,
            summary_code="PRESENCE_NOT_SUPPORTED",
            summary_parameters=params,
            input_links=links,
            next_actions=next_actions,
        )
    if anchor in provisional_union:
        limitation = Limitation(
            code=_UNCONFIRMED_LIMITATION,
            severity=LimitationSeverity.REVIEW_REQUIRED,
            message_parameters={"physical_presence_date": anchor.isoformat()},
            affected_input_ids=_uncertain_ids(inputs.trips),
        )
        return EvaluatedResult(
            requirement_key=KEY_PHYSICAL_PRESENCE,
            conclusion=Conclusion.INCOMPLETE.value,
            summary_code="PRESENCE_UNCERTAIN",
            summary_parameters=params,
            input_links=links,
            limitations=(limitation,),
        )
    return EvaluatedResult(
        requirement_key=KEY_PHYSICAL_PRESENCE,
        conclusion=Conclusion.SUPPORTED.value,
        summary_code="PRESENCE_CONFIRMED",
        summary_parameters=params,
        input_links=links,
    )


def _evaluate_absence_total(
    inputs: ResidenceAssessmentInputs,
    *,
    requirement_key: str,
    window_fn: Callable[[date], Window],
    band_fn: Callable[[int], Band],
    capped_summary_code: str,
    threshold: int,
) -> EvaluatedResult:
    """Shared body for §7.6 total and §7.7 final-year: trusted and provisional totals over
    the given window, banded, with the §6.2 sensitivity rule."""
    w = window_fn(inputs.application_date)
    trusted_spans = _spans(t for t in inputs.trips if t.is_trusted)
    trusted_total = count_in_window(absence_union(trusted_spans), w)
    provisional_total = count_in_window(absence_union(_spans(inputs.trips)), w)
    conclusion, summary_code, limitations = _threshold_conclusion(
        trusted_total, provisional_total, band_fn, capped_summary_code, _uncertain_ids(inputs.trips)
    )
    params: dict[str, object] = {
        "days": trusted_total,
        "provisional_days": provisional_total,
        "threshold": threshold,
        "window_start": w.start.isoformat(),
        "window_end": w.end.isoformat(),
        "trip_count": len(inputs.trips),
    }
    return EvaluatedResult(
        requirement_key=requirement_key,
        conclusion=conclusion.value,
        summary_code=summary_code,
        summary_parameters=params,
        input_links=(_app_date_link(inputs), *_travel_links(inputs.trips)),
        limitations=limitations,
    )


def _evaluate_travel_consistency(inputs: ResidenceAssessmentInputs) -> EvaluatedResult:
    """§7.8. A data-quality rule: it produces no eligibility conclusion of its own, only a
    consistency verdict over the travel records, so problems that would silently distort the
    totals are surfaced. Detections are structured limitations; conflicts/overlaps →
    INCONSISTENT, uncertain dates → INCOMPLETE, else SUPPORTED.

    Destination-aware duplicate detection (DUPLICATE_EVIDENCE) and unevidenced-trip detection
    (MISSING_EVIDENCE) need the destination and the evidence graph, which arrive in M4;
    absent-set overlap already catches identical-date trips here."""
    trips = inputs.trips
    anchor = physical_presence_date(inputs.application_date)
    qwindow = qualifying_window(inputs.application_date)
    absents = {
        t.travel_record_version_id: absent_dates(t.departure_date, t.return_date) for t in trips
    }
    limitations: list[Limitation] = []

    def _in_window(trip: TripInput) -> bool:
        # "Inside the qualifying period" (RULES_SPEC §7.8) is read as: the trip has at least
        # one absent day within the window. A trip wholly outside the window is informational
        # only and does not distort the totals, so its questionable dates are not flagged.
        return any(qwindow.contains(d) for d in absents[trip.travel_record_version_id])

    # CONFLICTING is window-scoped to match UNCERTAIN (RULES_SPEC §7.8): an out-of-window
    # conflict cannot affect the assessment, so it is not surfaced as an inconsistency.
    conflicting = [t for t in trips if t.date_confidence == "CONFLICTING" and _in_window(t)]
    if conflicting:
        limitations.append(
            Limitation(
                "CONFLICTING_SOURCE_DATES",
                LimitationSeverity.REVIEW_REQUIRED,
                affected_input_ids=tuple(str(t.travel_record_version_id) for t in conflicting),
            )
        )

    overlapping: set[uuid.UUID] = set()
    ids = list(absents)
    for i, left in enumerate(ids):
        for right in ids[i + 1 :]:
            if absents[left] & absents[right]:
                overlapping.update((left, right))
    if overlapping:
        limitations.append(
            Limitation(
                "OVERLAPPING_TRAVEL",
                LimitationSeverity.REVIEW_REQUIRED,
                affected_input_ids=tuple(sorted(str(i) for i in overlapping)),
            )
        )

    uncertain = [
        t for t in trips if t.date_confidence in _UNCERTAIN_CONFIDENCES and _in_window(t)
    ]
    if uncertain:
        limitations.append(
            Limitation(
                "UNCERTAIN_TRAVEL_DATE",
                LimitationSeverity.CAUTION,
                affected_input_ids=tuple(str(t.travel_record_version_id) for t in uncertain),
            )
        )

    boundary = [t for t in trips if anchor in absents[t.travel_record_version_id]]
    if boundary:
        limitations.append(
            Limitation(
                "NEAR_STANDARD_THRESHOLD",
                LimitationSeverity.CAUTION,
                message_parameters={"physical_presence_date": anchor.isoformat()},
                affected_input_ids=tuple(str(t.travel_record_version_id) for t in boundary),
            )
        )

    outside = [
        t
        for t in trips
        if absents[t.travel_record_version_id]
        and not any(qwindow.contains(d) for d in absents[t.travel_record_version_id])
    ]
    if outside:
        limitations.append(
            Limitation(
                "TRAVEL_OUTSIDE_WINDOW",
                LimitationSeverity.INFORMATION,
                affected_input_ids=tuple(str(t.travel_record_version_id) for t in outside),
            )
        )

    # Precedence: a conflict or an overlap is an inconsistency; uncertain dates are
    # incomplete; boundary/outside notes alone leave the records consistent.
    if conflicting:
        conclusion, code = Conclusion.INCONSISTENT, "TRAVEL_RECORDS_CONFLICT"
    elif overlapping:
        conclusion, code = Conclusion.INCONSISTENT, "TRAVEL_RECORDS_OVERLAP"
    elif uncertain:
        conclusion, code = Conclusion.INCOMPLETE, "TRAVEL_RECORDS_UNCERTAIN"
    else:
        conclusion, code = Conclusion.SUPPORTED, "TRAVEL_RECORDS_CONSISTENT"

    return EvaluatedResult(
        requirement_key=KEY_TRAVEL_CONSISTENCY,
        conclusion=conclusion.value,
        summary_code=code,
        input_links=(_app_date_link(inputs), *_travel_links(inputs.trips)),
        limitations=tuple(limitations),
    )


def evaluate_residence_requirements(inputs: ResidenceAssessmentInputs) -> list[EvaluatedResult]:
    """Evaluate the five residence rules over the case's application date and travel records.
    Trusted totals use only §6.1-gated trips; provisional totals include every active trip."""
    return [
        _evaluate_qualifying_period(inputs),
        _evaluate_physical_presence(inputs),
        _evaluate_absence_total(
            inputs,
            requirement_key=KEY_TOTAL_ABSENCES,
            window_fn=qualifying_window,
            band_fn=band_total_absences,
            capped_summary_code="TOTAL_ABSENCES_UNCONFIRMED_REVIEW",
            threshold=TOTAL_ABSENCE_THRESHOLD_DAYS,
        ),
        _evaluate_absence_total(
            inputs,
            requirement_key=KEY_FINAL_YEAR_ABSENCES,
            window_fn=final_year_window,
            band_fn=band_final_year_absences,
            capped_summary_code="FINAL_YEAR_UNCONFIRMED_REVIEW",
            threshold=FINAL_YEAR_ABSENCE_THRESHOLD_DAYS,
        ),
        _evaluate_travel_consistency(inputs),
    ]
