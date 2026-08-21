"""What issues *should* be open, given the case's durable state.

Pure functions over already-loaded state: no session, no clock, no I/O. That purity is
load-bearing rather than tidy. Reconciliation resolves any open issue this module does not
name, so anything non-deterministic here would open and close issues across otherwise
identical writes — a queue that flaps and a history full of noise.

**Everything derives from assessment results and their limitations, not from raw inputs.**
The evaluators already decide which travel records matter: `UNCERTAIN_TRAVEL_DATE` is
window-scoped, because a questionable date on a trip wholly outside the qualifying period
cannot distort a total (RULES_SPEC §7.8). Re-deriving that window here would be a second
implementation of a rule, and the two would drift. Travel records are read only to turn the
version ids a limitation names into the *record* ids and labels a user recognises.

Issues are derived from the **displayed** result, stale or current. A stale result's
conclusion is what the user is looking at, and suppressing its issues for the duration of
the stale window would make the near-threshold item vanish and reappear around every
recalculation. The `STALE_ASSESSMENT` issue alongside it is what says "not rechecked".
"""

from dataclasses import dataclass, field
from typing import Any

from app.issues.domain import Dismissibility, IssueSeverity, IssueType
from app.requirements.domain import Conclusion, Currency

AFFECTED_REQUIREMENT = "Requirement"
AFFECTED_TRAVEL_RECORD = "TravelRecord"
AFFECTED_CASE = "Case"

#: Limitation codes this module reads. Named here so a rename in the evaluator that this
#: module fails to follow is visible in one place rather than as a quietly empty queue.
LIMITATION_OVERLAPPING = "OVERLAPPING_TRAVEL"
LIMITATION_UNCERTAIN = "UNCERTAIN_TRAVEL_DATE"
LIMITATION_NARROW_MARGIN = "STATUS_PERIOD_NARROW_MARGIN"

#: Conclusions the prototype declines to assess on its own (UI/UX §10.2). Stopping is a
#: successful outcome, not a failure (CLAUDE.md §2.7), so these are surfaced as issues
#: rather than buried in a requirement nobody opens.
_UNSUPPORTED_CONCLUSIONS = frozenset(
    {Conclusion.REQUIRES_JUDGEMENT.value, Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED.value}
)


@dataclass(frozen=True)
class DesiredIssue:
    """One cause that should have a live issue. `deduplication_key` is its identity across
    episodes — resolve it, let the cause return, and the same key reopens the same row."""

    issue_type: IssueType
    severity: IssueSeverity
    dismissibility: Dismissibility
    title_code: str
    affected_object_type: str
    affected_object_id: str
    message_parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def deduplication_key(self) -> str:
        return f"{self.issue_type.value}:{self.affected_object_type}:{self.affected_object_id}"


@dataclass(frozen=True)
class RequirementSnapshot:
    """The slice of a displayed result this derivation needs — passed in rather than
    queried, so the derivation stays pure and unit-testable without a database."""

    requirement_key: str
    title: str
    conclusion: str
    currency: str
    stale_reason_code: str | None
    limitations: tuple[dict[str, Any], ...] = ()

    def limitation(self, code: str) -> dict[str, Any] | None:
        return next((lim for lim in self.limitations if lim.get("code") == code), None)


@dataclass(frozen=True)
class TravelSnapshot:
    """An active travel record. `record_id` is the identity that survives an edit — a
    corrected-but-still-uncertain trip must keep its issue rather than resolving one and
    opening another, which would read as progress where there is none."""

    record_id: str
    label: str
    is_uncertain: bool


@dataclass(frozen=True)
class LimitationTargets:
    """Which *records* the evaluator's limitations named, resolved from the version ids they
    actually carry, and whether that judgement is still current.

    `judged_records` is load-bearing. The in-window / out-of-window split decides whether
    an uncertain date is holding a figure back or is merely noted — the difference between
    an issue the user must act on and one they may set aside — and it comes from a
    limitation, which describes the case as the evaluator last saw it. A record the
    evaluator has never seen is *absent* from that limitation for the same reason a genuinely
    out-of-window one is, and treating the two alike would offer a Dismiss button for a trip
    that has never been assessed.

    So the two are distinguished by provenance: `judged_records` is what the consistency
    result actually read (its recorded input links). Absent from the limitation *and* judged
    means out of window. Absent and unjudged means unknown, and unknown takes the stronger
    shape.
    """

    overlapping_records: frozenset[str]
    uncertain_in_window_records: frozenset[str]
    judged_records: frozenset[str]


def derive(
    *,
    case_id: str,
    requirements: list[RequirementSnapshot],
    travel: list[TravelSnapshot],
    targets: LimitationTargets,
    recalculation_failed: bool = False,
) -> list[DesiredIssue]:
    """The complete desired open-issue set for a case.

    Complete is the operative word: reconciliation resolves anything open that this does
    not return, so a type omitted here is a type that silently clears itself.
    """
    issues: list[DesiredIssue] = []
    if recalculation_failed:
        issues.append(_processing_failure(case_id))
    for requirement in requirements:
        issues.extend(_requirement_issues(requirement))
    issues.extend(_travel_issues(travel, targets))
    return issues


def _processing_failure(case_id: str) -> DesiredIssue:
    """The last recalculation attempt failed (Domain §41.4).

    **Keyed on the case, not on the failed run.** The condition being reported is "the
    most recent attempt did not complete", which persists across repeated failures — so a
    second failure reshapes one open issue rather than resolving the first and opening a
    second. Keying on the run id would make every retry write a `SYSTEM_AUTO_RESOLVED`
    row for a failure that nothing resolved, which is precisely the false progress a
    resolution history exists to rule out.

    ACTION_REQUIRED rather than BLOCKING: nothing about the case is wrong, and the stale
    conclusions underneath are still the honest last word. Never dismissible — setting it
    aside would leave the user looking at figures the product knows are unrefreshed with
    nothing saying so.
    """
    return DesiredIssue(
        issue_type=IssueType.PROCESSING_FAILURE,
        severity=IssueSeverity.ACTION_REQUIRED,
        dismissibility=Dismissibility.NOT_DISMISSIBLE,
        title_code="ISSUE_RECALCULATION_FAILED",
        affected_object_type=AFFECTED_CASE,
        affected_object_id=case_id,
    )


def _requirement_issues(requirement: RequirementSnapshot) -> list[DesiredIssue]:
    issues: list[DesiredIssue] = []

    if requirement.currency == Currency.STALE.value:
        issues.append(
            DesiredIssue(
                issue_type=IssueType.STALE_ASSESSMENT,
                # ACTION_REQUIRED, not BLOCKING: a stale conclusion is not a defect in the
                # case, it is a conclusion awaiting a recheck the user triggers in one click.
                severity=IssueSeverity.ACTION_REQUIRED,
                # Never dismissible. Dismissing it would leave a conclusion the product
                # knows is out of date on screen with nothing saying so — false reassurance
                # by consent (CLAUDE.md §2.7). It clears itself on recalculation.
                dismissibility=Dismissibility.NOT_DISMISSIBLE,
                title_code="ISSUE_STALE_ASSESSMENT",
                affected_object_type=AFFECTED_REQUIREMENT,
                affected_object_id=requirement.requirement_key,
                message_parameters={
                    "requirement_title": requirement.title,
                    "reason_code": requirement.stale_reason_code or "",
                },
            )
        )

    if requirement.conclusion in _UNSUPPORTED_CONCLUSIONS:
        issues.append(
            DesiredIssue(
                issue_type=IssueType.UNSUPPORTED_COMPLEXITY,
                # REVIEW_REQUIRED, not BLOCKING. Every producer today is an absence band,
                # and RULES_SPEC bands 451 to 480 REQUIRES_JUDGEMENT *because* guidance
                # normally exercises discretion there — nothing in the product is gated on
                # it. Escalating is a successful outcome (CLAUDE.md §2.7), not a blockage,
                # and ranking it above everything would put the discretionary case at the
                # top of a queue where the definitive one (>900 days,
                # NOT_CURRENTLY_SATISFIED) is a requirement outcome and raises nothing.
                # BLOCKING is reserved for route scope, which cannot reach an active case.
                severity=IssueSeverity.REVIEW_REQUIRED,
                dismissibility=Dismissibility.NOT_DISMISSIBLE,
                title_code="ISSUE_UNSUPPORTED_COMPLEXITY",
                affected_object_type=AFFECTED_REQUIREMENT,
                affected_object_id=requirement.requirement_key,
                message_parameters={"requirement_title": requirement.title},
            )
        )
    elif requirement.conclusion == Conclusion.NEAR_THRESHOLD.value or requirement.limitation(
        LIMITATION_NARROW_MARGIN
    ):
        # Two triggers, two codes. The absence bands move with travel records; the status
        # holding period moves with the grant date and the application date, has no bands,
        # and cannot be shifted by a trip at all. One shared sentence would send the user to
        # an input that does not affect the figure.
        #
        # A narrow margin on a SUPPORTED conclusion is worth its own item: the requirement
        # reads "supported" and nothing else on the page says the margin is thin. Suppressed
        # when the conclusion is already unsupported-complexity — one requirement should not
        # produce two overlapping "watch this" items.
        narrow_margin = requirement.limitation(LIMITATION_NARROW_MARGIN) is not None
        issues.append(
            DesiredIssue(
                issue_type=IssueType.NEAR_THRESHOLD,
                severity=IssueSeverity.REVIEW_REQUIRED,
                dismissibility=Dismissibility.NOT_DISMISSIBLE,
                title_code=(
                    "ISSUE_NEAR_THRESHOLD_STATUS_PERIOD"
                    if narrow_margin
                    else "ISSUE_NEAR_THRESHOLD_ABSENCES"
                ),
                affected_object_type=AFFECTED_REQUIREMENT,
                affected_object_id=requirement.requirement_key,
                message_parameters={"requirement_title": requirement.title},
            )
        )

    return issues


def _travel_issues(travel: list[TravelSnapshot], targets: LimitationTargets) -> list[DesiredIssue]:
    by_record = {trip.record_id: trip for trip in travel}
    issues: list[DesiredIssue] = []

    # One issue per overlapping record, not one per pair: the user fixes an overlap by
    # editing a record, and a pair has no single affected object to name (§36.1).
    for record_id in sorted(targets.overlapping_records):
        trip = by_record.get(record_id)
        if trip is None:
            continue
        issues.append(
            DesiredIssue(
                issue_type=IssueType.OVERLAPPING_TRAVEL,
                severity=IssueSeverity.REVIEW_REQUIRED,
                dismissibility=Dismissibility.NOT_DISMISSIBLE,
                title_code="ISSUE_OVERLAPPING_TRAVEL",
                affected_object_type=AFFECTED_TRAVEL_RECORD,
                affected_object_id=trip.record_id,
                message_parameters={"destination": trip.label},
            )
        )

    for trip in travel:
        if not trip.is_uncertain:
            continue
        # Out-of-window is the weaker shape — information the user may set aside — so it is
        # claimed only about a record the evaluator has actually judged. A trip added since
        # the last assessment is absent from the limitation because nothing has looked at it
        # yet, and saying "this does not affect any figure" about it would be a guess with a
        # Dismiss button beside it.
        in_window = (
            trip.record_id in targets.uncertain_in_window_records
            or trip.record_id not in targets.judged_records
        )
        issues.append(
            DesiredIssue(
                issue_type=IssueType.UNCERTAIN_TRAVEL_DATE,
                # A questionable date inside the qualifying period is holding a figure back
                # under the §6.2 sensitivity rule, so it needs an action. Outside the
                # period it changes nothing, so it is information the user may set aside —
                # the one dismissible case in the product today.
                severity=IssueSeverity.ACTION_REQUIRED if in_window else IssueSeverity.INFORMATION,
                dismissibility=(
                    Dismissibility.NOT_DISMISSIBLE if in_window else Dismissibility.DISMISSIBLE
                ),
                title_code=(
                    "ISSUE_UNCERTAIN_TRAVEL_DATE" if in_window else "ISSUE_UNCERTAIN_DATE_OUTSIDE"
                ),
                affected_object_type=AFFECTED_TRAVEL_RECORD,
                affected_object_id=trip.record_id,
                message_parameters={"destination": trip.label},
            )
        )

    return issues
