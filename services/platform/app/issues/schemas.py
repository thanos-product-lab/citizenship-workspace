"""The IssueQueueProjection (Domain §44.5) as wire types.

Grouped open issues, priority, reason, why it matters, available actions, and resolution
history. All prose is rendered server-side from `title_code` + `message_parameters`, never
assembled on the client — the same discipline as requirement summaries, so the deterministic
copy rules in `messages.py` apply once and hold everywhere.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.issues.domain import (
    RECHECK_TYPES,
    Dismissibility,
    Issue,
    IssueResolution,
    IssueSeverity,
    IssueStatus,
    IssueType,
    count_actions,
)
from app.requirements.messages import (
    render_issue_body,
    render_issue_impact,
    render_issue_title,
)

#: Issue type → action group, where the *type* names a more specific action than its
#: severity implies. Severity alone put "Recheck Total absences" and "We could not recheck
#: your conclusions" under "Confirm information", which is not what either asks for — and
#: because the heading labels an `aria-labelledby` region, a screen-reader user navigating
#: by landmark was routed away from the one item explaining why their figures are stale
#: (WCAG 2.4.6). Both types are cleared by the same case-wide recalculation, which is what
#: makes them one group.
TYPE_ACTION_GROUPS: dict[str, str] = dict.fromkeys(RECHECK_TYPES, "RECHECK_CONCLUSIONS")

#: Severity → the group a user acts on, per UI/UX §10 ("group issues by user action"). The
#: fallback when the type says nothing more specific.
ACTION_GROUPS: dict[str, str] = {
    IssueSeverity.BLOCKING.value: "RESOLVE_TO_CONTINUE",
    IssueSeverity.ACTION_REQUIRED.value: "CONFIRM_INFORMATION",
    IssueSeverity.REVIEW_REQUIRED.value: "REVIEW_CAREFULLY",
    IssueSeverity.INFORMATION.value: "FOR_YOUR_AWARENESS",
}

#: Ordering within the queue: most consequential first. Not a score — a fixed severity
#: ranking, which is the only ordering this product commits to (CLAUDE.md §2.6).
_SEVERITY_ORDER = {
    IssueSeverity.BLOCKING.value: 0,
    IssueSeverity.ACTION_REQUIRED.value: 1,
    IssueSeverity.REVIEW_REQUIRED.value: 2,
    IssueSeverity.INFORMATION.value: 3,
}

#: Precedence *within* a severity. Only one type claims it: a failed recalculation is the
#: reason the stale items beside it are still stale, and ordering by time alone puts it
#: below them — it opens last, because it is a consequence of trying to clear them. The
#: reader would meet the effects before the cause.
_TYPE_PRECEDENCE = {IssueType.PROCESSING_FAILURE.value: 0}
_DEFAULT_PRECEDENCE = 1


class IssueResolutionView(BaseModel):
    resolution_type: str
    resolved_by: str
    resolved_at: datetime
    notes: str | None = None

    @classmethod
    def of(cls, resolution: IssueResolution) -> "IssueResolutionView":
        return cls(
            resolution_type=resolution.resolution_type,
            resolved_by=resolution.resolved_by,
            resolved_at=resolution.resolved_at,
            notes=resolution.notes,
        )


class IssueView(BaseModel):
    id: uuid.UUID
    issue_type: str
    severity: str
    status: str
    dismissibility: str
    action_group: str
    title: str
    body: str | None = None
    impact: str | None = None
    affected_object_type: str
    affected_object_id: str
    opened_at: datetime
    resolved_at: datetime | None = None
    reopened_at: datetime | None = None
    #: True when this cause has been raised before, resolved, and has come back. The queue
    #: says so rather than presenting a recurrence as a first occurrence.
    has_recurred: bool = False
    resolutions: list[IssueResolutionView] = []

    @classmethod
    def of(cls, issue: Issue, resolutions: list[IssueResolution]) -> "IssueView":
        parameters = dict(issue.message_parameters)
        return cls(
            id=issue.id,
            issue_type=issue.issue_type,
            severity=issue.severity,
            status=issue.status,
            dismissibility=issue.dismissibility,
            action_group=TYPE_ACTION_GROUPS.get(
                issue.issue_type, ACTION_GROUPS.get(issue.severity, "REVIEW_CAREFULLY")
            ),
            # An unknown title_code renders its code rather than an invented sentence: the
            # screen shows something traceable, and `test_messages.py` fails the packaging
            # bug that produced it.
            title=render_issue_title(issue.title_code, parameters) or issue.title_code,
            body=render_issue_body(issue.title_code, parameters),
            impact=render_issue_impact(issue.title_code, parameters),
            affected_object_type=issue.affected_object_type,
            affected_object_id=issue.affected_object_id,
            opened_at=issue.opened_at,
            resolved_at=issue.resolved_at,
            reopened_at=issue.reopened_at,
            has_recurred=issue.reopened_at is not None,
            resolutions=[IssueResolutionView.of(r) for r in resolutions],
        )

    @property
    def is_dismissible(self) -> bool:
        return self.dismissibility == Dismissibility.DISMISSIBLE.value


class IssueGroupView(BaseModel):
    """Open issues sharing one user action (UI/UX §10)."""

    action_group: str
    issues: list[IssueView]

    @property
    def count(self) -> int:
        return len(self.issues)


class RecheckedCheckView(BaseModel):
    """One conclusion the update would recheck, named and addressable."""

    issue_id: uuid.UUID
    requirement_key: str
    requirement_title: str


class RecheckTaskView(BaseModel):
    """Every open recheck-type issue, presented as the one task they are (ADR-0033).

    The stored issues are untouched: each keeps its own identity, history and reopening
    (ADR-0015), and each still appears on its own in `history` once resolved. This is only
    how the open ones are shown, because one command clears them all and four cards for
    one button read as four jobs.

    Prose is rendered here, not in the client, like every other issue sentence.
    """

    #: The last recalculation failed, so the command is a retry.
    failed: bool
    title: str
    body: str
    impact: str
    checks: list[RecheckedCheckView]
    #: The stored issues behind the task, in queue order (a failure first, since it is
    #: why the stale ones are still stale). Kept so nothing about an individual issue is
    #: lost by presenting them together.
    issues: list[IssueView]


def _recheck_task(
    open_issues: list[Issue], views: dict[uuid.UUID, IssueView], ordered: list[IssueView]
) -> RecheckTaskView | None:
    rechecks = [i for i in open_issues if i.issue_type in RECHECK_TYPES]
    if not rechecks:
        return None
    failure = next(
        (i for i in rechecks if i.issue_type == IssueType.PROCESSING_FAILURE.value), None
    )
    stale = sorted(
        (i for i in rechecks if i.issue_type == IssueType.STALE_ASSESSMENT.value),
        key=lambda i: i.affected_object_id,
    )
    checks = [
        RecheckedCheckView(
            issue_id=i.id,
            requirement_key=i.affected_object_id,
            requirement_title=str(
                dict(i.message_parameters).get("requirement_title", i.affected_object_id)
            ),
        )
        for i in stale
    ]
    n = len(checks)
    behind = [v for v in ordered if v.issue_type in RECHECK_TYPES]
    if failure is not None:
        # The failure's own server-rendered sentences: they already say what happened and
        # that the figures were left alone, and a second wording would drift from them.
        view = views[failure.id]
        return RecheckTaskView(
            failed=True,
            title=view.title,
            body=view.body or "",
            impact=view.impact or "",
            checks=checks,
            issues=behind,
        )
    return RecheckTaskView(
        failed=False,
        title="Update assessment",
        body=(
            f"{n} {'result is' if n == 1 else 'results are'} from before your last change "
            f"and {'has' if n == 1 else 'have'} not been rechecked. One update rechecks "
            f"{'it' if n == 1 else 'all of them'}."
        ),
        impact=(
            f"Until you update, {'this result' if n == 1 else 'these results'} may not match "
            "your information."
        ),
        checks=checks,
        issues=behind,
    )


class IssueQueue(BaseModel):
    """Domain §44.5.

    `open_count` counts OPEN and IN_PROGRESS only. A dismissed issue is not awaiting the
    user, and counting it would leave a badge nobody can clear.
    """

    case_id: uuid.UUID
    open_count: int
    #: What the user has to do, with every recheck counted once (ADR-0033). The number the
    #: navigation shows; `open_count` stays the plain total.
    action_count: int
    #: Open INFORMATION items: shown, and never counted as something to do.
    awareness_count: int
    #: The open recheck-type issues as one task, or null when there are none. They are
    #: left out of `groups` so the same issue is not shown twice.
    recheck: RecheckTaskView | None = None
    groups: list[IssueGroupView]
    #: Resolved and dismissed issues, newest first. Retained rather than deleted (§36.6):
    #: "this was raised and cleared" is part of what the case says about itself.
    history: list[IssueView]

    @classmethod
    def build(
        cls,
        *,
        case_id: uuid.UUID,
        issues: list[Issue],
        resolutions_by_issue: dict[uuid.UUID, list[IssueResolution]],
    ) -> "IssueQueue":
        open_views: list[IssueView] = []
        open_issues: list[Issue] = []
        history: list[IssueView] = []
        for issue in issues:
            view = IssueView.of(issue, resolutions_by_issue.get(issue.id, []))
            if issue.status in (IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value):
                open_views.append(view)
                open_issues.append(issue)
            else:
                history.append(view)

        # Every issue from one reconcile shares `opened_at`, so severity and time alone
        # leave ties to Postgres' arbitrary row order and the queue reorders between
        # requests. The affected object is the stable tiebreaker.
        open_views.sort(
            key=lambda v: (
                _SEVERITY_ORDER.get(v.severity, 9),
                _TYPE_PRECEDENCE.get(v.issue_type, _DEFAULT_PRECEDENCE),
                v.opened_at,
                v.affected_object_id,
            )
        )
        grouped: dict[str, list[IssueView]] = {}
        for view in open_views:
            if view.issue_type in RECHECK_TYPES:
                continue
            grouped.setdefault(view.action_group, []).append(view)

        counts = count_actions([(v.issue_type, v.severity) for v in open_views])
        return cls(
            case_id=case_id,
            open_count=len(open_views),
            action_count=counts.actions,
            awareness_count=counts.awareness,
            recheck=_recheck_task(open_issues, {v.id: v for v in open_views}, open_views),
            groups=[
                IssueGroupView(action_group=group, issues=views) for group, views in grouped.items()
            ],
            history=history,
        )
