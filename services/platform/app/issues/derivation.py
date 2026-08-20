"""What issues *should* be open, given the case's durable state.

Pure functions over already-loaded state: no session, no clock, no I/O. That purity is
load-bearing rather than tidy. Reconciliation resolves any open issue this module does not
name, so anything non-deterministic here would open and close issues across otherwise
identical writes — a queue that flaps, and a resolution history full of noise. Anything
that varies with wall-clock time in particular must not appear.

At this slice one type is derived: `STALE_ASSESSMENT`, one per requirement whose displayed
result is STALE. Per-requirement rather than per-case because Domain §36.1 gives an issue a
single `affected_object`, and because each then resolves independently when its own result
is superseded — so a recalculation that refreshed some requirements and not others is
represented honestly rather than as one all-or-nothing item.
"""

from dataclasses import dataclass, field
from typing import Any

from app.issues.domain import Dismissibility, IssueSeverity, IssueType
from app.requirements.domain import Currency

#: The requirement a stale conclusion belongs to. Not a database row: the stable public
#: requirement key, which is what the queue links back to.
AFFECTED_REQUIREMENT = "Requirement"


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
class StaleRequirement:
    """The slice of a displayed result this derivation needs — passed in rather than
    queried, so the derivation stays pure and unit-testable without a database."""

    requirement_key: str
    title: str
    currency: str
    stale_reason_code: str | None


def derive(*, requirements: list[StaleRequirement]) -> list[DesiredIssue]:
    """The complete desired open-issue set for a case.

    Complete is the operative word: reconciliation resolves anything open that this does
    not return, so a type omitted here is a type that silently clears itself.
    """
    return [_stale_issue(requirement) for requirement in requirements if _is_stale(requirement)]


def _is_stale(requirement: StaleRequirement) -> bool:
    return requirement.currency == Currency.STALE.value


def _stale_issue(requirement: StaleRequirement) -> DesiredIssue:
    return DesiredIssue(
        issue_type=IssueType.STALE_ASSESSMENT,
        # ACTION_REQUIRED, not BLOCKING: a stale conclusion is not a defect in the case, it
        # is a conclusion awaiting a recheck the user can trigger in one click.
        severity=IssueSeverity.ACTION_REQUIRED,
        # Never dismissible. Dismissing it would leave a conclusion the product knows is
        # out of date sitting on screen with nothing saying so — false reassurance by
        # consent (CLAUDE.md §2.7). It clears itself on recalculation instead.
        dismissibility=Dismissibility.NOT_DISMISSIBLE,
        title_code="ISSUE_STALE_ASSESSMENT",
        affected_object_type=AFFECTED_REQUIREMENT,
        affected_object_id=requirement.requirement_key,
        message_parameters={
            "requirement_title": requirement.title,
            "reason_code": requirement.stale_reason_code or "",
        },
    )
