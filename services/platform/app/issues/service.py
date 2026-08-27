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

from app.assessments.domain import AssessmentRunStatus
from app.assessments.repository import AssessmentRepository
from app.evidence.repository import EvidenceRepository
from app.issues.derivation import (
    LIMITATION_DUPLICATE_RECORD,
    LIMITATION_MISSING_EVIDENCE,
    LIMITATION_OVERLAPPING,
    LIMITATION_UNCERTAIN,
    DesiredIssue,
    EvidenceSnapshot,
    LimitationTargets,
    RequirementSnapshot,
    TravelSnapshot,
    derive,
)
from app.issues.domain import (
    Dismissibility,
    Issue,
    IssueDismissed,
    IssueSeverity,
    IssuesReconciled,
    IssueStatus,
    ResolutionType,
)
from app.issues.repository import IssueRepository
from app.requirements.evaluation import KEY_TRAVEL_CONSISTENCY, UNCERTAIN_CONFIDENCES
from app.residence.repository import TravelRecordRepository
from app.shared.errors import IllegalTransition
from app.shared.unit_of_work import UnitOfWork

#: Who a system-driven resolution is attributed to. Not a user id: nobody performed it.
SYSTEM_ACTOR = "system"


@dataclass(frozen=True)
class ReconciliationOutcome:
    """What moved. Deduplication keys rather than counts, so the caller and the audit log
    can both say which causes changed."""

    opened: tuple[str, ...]
    resolved: tuple[str, ...]
    reopened: tuple[str, ...]

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
    # The session is autoflush=False and reconciliation runs mid-command, so pending travel
    # writes are invisible to a query until flushed: a new record has no version row yet, an
    # edited one still joins to its previous version, a removed one still reads ACTIVE. The
    # derivation would then see half pre-write and half post-write state, which is not the
    # "pure function of durable state" it is documented to be.
    session.flush()
    requirements = _requirement_snapshots(session, case_id)
    desired = derive(
        case_id=str(case_id),
        requirements=requirements,
        travel=_travel_snapshots(session, case_id),
        targets=_limitation_targets(session, case_id, requirements),
        recalculation_failed=_recalculation_failed(session, case_id),
        evidence=_evidence_snapshots(session, case_id),
        has_ever_held_evidence=EvidenceRepository.case_has_ever_held_evidence(
            session, case_id=case_id
        ),
    )
    desired_by_key = {issue.deduplication_key: issue for issue in desired}

    live_issues = IssueRepository.list_live(session, case_id)
    live_by_key = {issue.deduplication_key: issue for issue in live_issues}

    opened: list[str] = []
    reopened: list[str] = []
    for key, wanted in desired_by_key.items():
        live = live_by_key.get(key)
        if live is not None:
            # Already represented — including one the user dismissed. Its *shape* is
            # reconciled too, not only its parameters: one cause can present differently
            # over time. An uncertain travel date is INFORMATION and dismissible while it
            # sits outside the qualifying period, and ACTION_REQUIRED and not dismissible
            # once the application date moves it inside. Freezing the shape at open time
            # would leave the queue saying "this does not affect any figure", with a Dismiss
            # button beside it, about a date now holding a figure back.
            if _reshape(live, wanted) and live.status == IssueStatus.DISMISSED.value:
                # The user set aside the issue *as it was presented*. It is presented
                # differently now, so the dismissal is spent and the item comes back.
                live.reopen(at=now)
                reopened.append(key)
            continue
        existing = IssueRepository.get_by_deduplication_key(session, case_id, key)
        if existing is not None and existing.status == IssueStatus.RESOLVED.value:
            existing.reopen(at=now)
            # The new episode's parameters, not the old one's. A cause can return for a
            # different reason — staled by a date change where it was last staled by a trip
            # edit — and reopening with the previous payload would misreport why.
            existing.message_parameters = dict(wanted.message_parameters)
            reopened.append(key)
        else:
            IssueRepository.add(session, _new_issue(case_id, wanted, now))
            opened.append(key)

    resolved: list[str] = []
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
        resolved.append(key)

    session.flush()
    outcome = ReconciliationOutcome(
        opened=tuple(sorted(opened)),
        resolved=tuple(sorted(resolved)),
        reopened=tuple(sorted(reopened)),
    )
    if outcome.changed:
        uow.emit(
            IssuesReconciled(
                aggregate_id=case_id,
                opened=outcome.opened,
                resolved=outcome.resolved,
                reopened=outcome.reopened,
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
    # Only a live issue can be set aside. Dismissing a RESOLVED one would pull a history
    # row back into the live set — where it suppresses its cause reopening — and clear the
    # timestamp of the resolution that actually happened.
    if issue.status not in (IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value):
        raise IllegalTransition("only an open issue can be dismissed")

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


def _recalculation_failed(session: Session, case_id: uuid.UUID) -> bool:
    """Whether the case's most recent assessment run failed (Domain §41.4).

    Derived from the run row rather than signalled by the failure handler, so the whole
    lifecycle is one diff like every other type: the failure opens the issue because the
    latest run is FAILED, and the next successful run closes it because the latest run is
    no longer FAILED. No special-case cleanup, and nothing to forget on a path added later
    — a recalculation triggered from somewhere new inherits both halves for free.
    """
    latest = AssessmentRepository.get_latest_finished_run(session, case_id)
    return latest is not None and latest.status == AssessmentRunStatus.FAILED.value


def _requirement_snapshots(session: Session, case_id: uuid.UUID) -> list[RequirementSnapshot]:
    """The displayed result for every requirement, reduced to what derivation reads. Reads
    only — nothing in this module writes an assessment row (§36.6)."""
    return [
        RequirementSnapshot(
            requirement_key=definition.requirement_key,
            title=definition.title,
            conclusion=result.conclusion,
            currency=result.currency,
            stale_reason_code=result.stale_reason_code,
            limitations=tuple(result.limitations or ()),
        )
        for definition, result in AssessmentRepository.list_requirements_with_active_result(
            session, case_id
        )
        if result is not None
    ]


def _travel_snapshots(session: Session, case_id: uuid.UUID) -> list[TravelSnapshot]:
    """Active travel records, so a limitation naming version ids can be turned into the
    record identity and destination a user recognises.

    `is_uncertain` mirrors the evaluator's own definition (`_UNCERTAIN_CONFIDENCES`) rather
    than restating it: a record whose date confidence is not exact. Whether that matters —
    whether the trip falls inside the qualifying period — is the evaluator's judgement, read
    from its limitation, never recomputed here.
    """
    return [
        TravelSnapshot(
            record_id=str(record.id),
            label=version.destination_label,
            is_uncertain=version.date_confidence in UNCERTAIN_CONFIDENCES,
        )
        for record, version in TravelRecordRepository.list_active_with_current_version(
            session, case_id
        )
    ]


def _limitation_targets(
    session: Session, case_id: uuid.UUID, requirements: list[RequirementSnapshot]
) -> LimitationTargets:
    """Turn the travel-record *version* ids a limitation carries into the *record* ids the
    queue is keyed on, and say whether the window judgement behind them is still current.

    Versions are resolved through the whole version history, not the current ones. A stale
    result names the versions the evaluator read at the time; matching those against current
    versions only would silently drop them, and an overlap the rules found would look
    resolved.
    """
    versions_to_records = TravelRecordRepository.map_versions_to_records(session, case_id)

    def _records(code: str) -> frozenset[str]:
        records: set[str] = set()
        for requirement in requirements:
            limitation = requirement.limitation(code)
            if limitation is None:
                continue
            for version_id in limitation.get("affected_input_ids", []):
                record_id = versions_to_records.get(str(version_id))
                if record_id is not None:
                    records.add(record_id)
        return frozenset(records)

    # Which records the window judgement actually covers: the travel inputs the consistency
    # result recorded reading. Provenance answering a question about provenance.
    judged = {
        record_id
        for version_id in AssessmentRepository.list_travel_input_version_ids(
            session, case_id, KEY_TRAVEL_CONSISTENCY
        )
        if (record_id := versions_to_records.get(str(version_id))) is not None
    }

    return LimitationTargets(
        overlapping_records=_records(LIMITATION_OVERLAPPING),
        uncertain_in_window_records=_records(LIMITATION_UNCERTAIN),
        judged_records=frozenset(judged),
        unevidenced_records=_records(LIMITATION_MISSING_EVIDENCE),
        duplicate_records=_records(LIMITATION_DUPLICATE_RECORD),
    )


def _evidence_snapshots(session: Session, case_id: uuid.UUID) -> list[EvidenceSnapshot]:
    """The case's **live** documents, for duplicate detection.

    Live only: a tombstone has no checksum left to compare, and a deleted document cannot
    duplicate anything.

    This no longer serves the coverage gate. It did, as `bool(evidence)` — one read serving
    both — until deletion arrived and showed the two questions were never the same one. The
    gate asks whether the user has *ever* provided a document, which tombstones answer;
    duplicate detection asks which documents are here *now*. Collapsing them made deleting
    the last document close every coverage item.
    """
    return [
        EvidenceSnapshot(item_id=str(item_id), display_name=display_name, checksum=checksum)
        for item_id, display_name, checksum in EvidenceRepository.fingerprints_for_case(
            session, case_id=case_id
        )
    ]


def _reshape(issue: Issue, wanted: DesiredIssue) -> bool:
    """Bring a live issue in line with what it should look like now. Returns True when the
    change is an *escalation* — the item became more serious or stopped being dismissible —
    which is the only case where a dismissal should not survive it."""
    escalated = (
        issue.dismissibility == Dismissibility.DISMISSIBLE.value
        and wanted.dismissibility is Dismissibility.NOT_DISMISSIBLE
    ) or _SEVERITY_RANK[wanted.severity.value] > _SEVERITY_RANK.get(issue.severity, 0)

    issue.severity = wanted.severity.value
    issue.dismissibility = wanted.dismissibility.value
    issue.title_code = wanted.title_code
    if issue.message_parameters != wanted.message_parameters:
        issue.message_parameters = dict(wanted.message_parameters)
    return escalated


#: How serious each severity is, for deciding whether a re-shape is an escalation. Mirrors
#: the queue's own ordering in `schemas._SEVERITY_ORDER`, inverted.
_SEVERITY_RANK = {
    IssueSeverity.INFORMATION.value: 0,
    IssueSeverity.REVIEW_REQUIRED.value: 1,
    IssueSeverity.ACTION_REQUIRED.value: 2,
    IssueSeverity.BLOCKING.value: 3,
}
