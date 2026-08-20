"""The IssueDerivationService (Domain §48.8): reconcile the queue against durable state.

One entry point, `reconcile`, called from every seam that can change what is wrong with a
case — the invalidation seam and the end of a recalculation at this slice — always on the
caller's unit of work, so issues commit atomically with their cause or not at all.

**Reconciliation, not event handlers.** The service computes the complete desired set
(`derivation.derive`) and diffs it against what is stored:

    desired, no live row      → open, or reopen a resolved row with the same key
    live row, not desired     → resolve, writing an IssueResolution
    live row, still desired   → leave alone (including a dismissed one)

Auto-resolution and reopening then fall out of one diff rather than out of N handlers that
each have to remember to clean up after themselves. The price is that derivation must be a
pure function of durable state — see `derivation`.

This module imports **repositories only**, never another module's service: `residence` and
`assessments` call into it, so importing their services back would cycle. The same
discipline `invalidation.py` follows.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.assessments.repository import AssessmentRepository
from app.issues.derivation import DesiredIssue, StaleRequirement, derive
from app.issues.domain import (
    Dismissibility,
    Issue,
    IssueDismissed,
    IssuesReconciled,
    IssueStatus,
    ResolutionType,
)
from app.issues.repository import IssueRepository
from app.shared.errors import IllegalTransition
from app.shared.unit_of_work import UnitOfWork

#: Who a system-driven resolution is attributed to. Not a user id: nobody performed it.
SYSTEM_ACTOR = "system"


@dataclass(frozen=True)
class ReconciliationOutcome:
    opened: int
    resolved: int
    reopened: int
    issue_types: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.opened or self.resolved or self.reopened)


def reconcile(
    session: Session, uow: UnitOfWork, *, case_id: uuid.UUID, at: datetime | None = None
) -> ReconciliationOutcome:
    """Bring the case's issue queue into line with its current state.

    Idempotent by construction: a second call with unchanged state computes the same
    desired set, finds every cause already live, and changes nothing. `test_issues.py`
    asserts that rather than trusting it.
    """
    now = at or datetime.now(UTC)
    desired = derive(requirements=_stale_requirements(session, case_id))
    desired_by_key = {issue.deduplication_key: issue for issue in desired}

    live = IssueRepository.list_live(session, case_id)
    live_by_key = {issue.deduplication_key: issue for issue in live}

    opened = reopened = 0
    for key, wanted in desired_by_key.items():
        if key in live_by_key:
            continue  # already represented — including one the user dismissed
        existing = IssueRepository.get_by_deduplication_key(session, case_id, key)
        if existing is not None and existing.status == IssueStatus.RESOLVED.value:
            existing.reopen(at=now)
            reopened += 1
        else:
            IssueRepository.add(session, _new_issue(case_id, wanted, now))
            opened += 1

    resolved = 0
    for key, issue in live_by_key.items():
        if key in desired_by_key:
            continue
        issue.resolve(at=now)
        IssueRepository.record_resolution(
            session,
            issue_id=issue.id,
            # The cause going away *is* the resolution; nobody acted on the issue itself.
            resolution_type=ResolutionType.SYSTEM_AUTO_RESOLVED,
            resolved_by=SYSTEM_ACTOR,
            at=now,
        )
        resolved += 1

    session.flush()
    outcome = ReconciliationOutcome(
        opened=opened,
        resolved=resolved,
        reopened=reopened,
        issue_types=tuple(sorted({issue.issue_type.value for issue in desired})),
    )
    if outcome.changed:
        uow.emit(
            IssuesReconciled(
                aggregate_id=case_id,
                opened=opened,
                resolved=resolved,
                reopened=reopened,
                issue_types=outcome.issue_types,
            ),
            case_id=case_id,
            action="issues.reconciled",
            target_type="ApplicationCase",
            target_id=case_id,
        )
    return outcome


def dismiss(
    session: Session,
    uow: UnitOfWork,
    *,
    case_id: uuid.UUID,
    issue_id: uuid.UUID,
    actor_id: str,
    at: datetime | None = None,
) -> Issue:
    """Set an issue aside. Refuses anything not marked DISMISSIBLE with a domain error
    (→ 409), not a 403: this is a rule about the issue, not about who is asking."""
    issue = IssueRepository.get(session, case_id, issue_id)
    if issue is None:
        raise IssueNotFound(str(issue_id))
    if issue.dismissibility != Dismissibility.DISMISSIBLE.value:
        raise IllegalTransition("this issue cannot be dismissed")
    if issue.status == IssueStatus.DISMISSED.value:
        return issue

    now = at or datetime.now(UTC)
    issue.dismiss(at=now)
    IssueRepository.record_resolution(
        session,
        issue_id=issue.id,
        resolution_type=ResolutionType.USER_DISMISSED,
        resolved_by=actor_id,
        at=now,
    )
    uow.emit(
        IssueDismissed(aggregate_id=issue.id, issue_type=issue.issue_type),
        case_id=case_id,
        action="issues.dismissed",
        target_type="Issue",
        target_id=issue.id,
    )
    return issue


class IssueNotFound(Exception):
    """No such issue in this case."""


def _new_issue(case_id: uuid.UUID, desired: DesiredIssue, at: datetime) -> Issue:
    return Issue.open_new(
        case_id=case_id,
        issue_type=desired.issue_type,
        severity=desired.severity,
        dismissibility=desired.dismissibility,
        deduplication_key=desired.deduplication_key,
        title_code=desired.title_code,
        affected_object_type=desired.affected_object_type,
        affected_object_id=desired.affected_object_id,
        message_parameters=desired.message_parameters,
        at=at,
    )


def _stale_requirements(session: Session, case_id: uuid.UUID) -> list[StaleRequirement]:
    """Read the displayed result for every requirement and hand the derivation the fields
    it needs. Reads only — nothing here writes an assessment row (§36.6)."""
    return [
        StaleRequirement(
            requirement_key=definition.requirement_key,
            title=definition.title,
            currency=result.currency,
            stale_reason_code=result.stale_reason_code,
        )
        for definition, result in AssessmentRepository.list_requirements_with_active_result(
            session, case_id
        )
        if result is not None
    ]
