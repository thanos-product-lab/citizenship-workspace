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
    version_id: str
    label: str
    is_uncertain: bool


def derive(
    *, requirements: list[RequirementSnapshot], travel: list[TravelSnapshot]
) -> list[DesiredIssue]:
    """The complete desired open-issue set for a case.

    Complete is the operative word: reconciliation resolves anything open that this does
    not return, so a type omitted here is a type that silently clears itself.
    """
    issues: list[DesiredIssue] = []
    for requirement in requirements:
        issues.extend(_requirement_issues(requirement))
    issues.extend(_travel_issues(requirements, travel))
    return issues


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
                severity=IssueSeverity.BLOCKING,
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
        # A narrow margin on a SUPPORTED conclusion is the case worth having separately: the
        # requirement reads "supported" and nothing else on the page says the margin is
        # thin. Suppressed when the conclusion is already unsupported-complexity — one
        # requirement should not produce two overlapping "watch this" items.
        issues.append(
            DesiredIssue(
                issue_type=IssueType.NEAR_THRESHOLD,
                severity=IssueSeverity.REVIEW_REQUIRED,
                dismissibility=Dismissibility.NOT_DISMISSIBLE,
                title_code="ISSUE_NEAR_THRESHOLD",
                affected_object_type=AFFECTED_REQUIREMENT,
                affected_object_id=requirement.requirement_key,
                message_parameters={"requirement_title": requirement.title},
            )
        )

    return issues


def _travel_issues(
    requirements: list[RequirementSnapshot], travel: list[TravelSnapshot]
) -> list[DesiredIssue]:
    by_version = {trip.version_id: trip for trip in travel}
    overlapping = _affected_versions(requirements, LIMITATION_OVERLAPPING)
    uncertain_in_window = _affected_versions(requirements, LIMITATION_UNCERTAIN)

    issues: list[DesiredIssue] = []

    # One issue per overlapping record, not one per pair: the user fixes an overlap by
    # editing a record, and a pair has no single affected object to name (§36.1).
    for version_id in sorted(overlapping):
        trip = by_version.get(version_id)
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
        in_window = trip.version_id in uncertain_in_window
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


def _affected_versions(requirements: list[RequirementSnapshot], code: str) -> set[str]:
    """Travel-record *version* ids named by a limitation, across every displayed result."""
    affected: set[str] = set()
    for requirement in requirements:
        limitation = requirement.limitation(code)
        if limitation is None:
            continue
        affected.update(str(i) for i in limitation.get("affected_input_ids", []))
    return affected
