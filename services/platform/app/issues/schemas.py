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
    Dismissibility,
    Issue,
    IssueResolution,
    IssueSeverity,
    IssueStatus,
    IssueType,
)
from app.requirements.messages import (
    render_issue_body,
    render_issue_impact,
    render_issue_title,
)

#: Severity → the group a user acts on, per UI/UX §10 ("group issues by user action").
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
            action_group=ACTION_GROUPS.get(issue.severity, "REVIEW_CAREFULLY"),
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


class IssueQueue(BaseModel):
    """Domain §44.5.

    `open_count` counts OPEN and IN_PROGRESS only. A dismissed issue is not awaiting the
    user, and counting it would leave a badge nobody can clear.
    """

    case_id: uuid.UUID
    open_count: int
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
        history: list[IssueView] = []
        for issue in issues:
            view = IssueView.of(issue, resolutions_by_issue.get(issue.id, []))
            if issue.status in (IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value):
                open_views.append(view)
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
            grouped.setdefault(view.action_group, []).append(view)

        return cls(
            case_id=case_id,
            open_count=len(open_views),
            groups=[
                IssueGroupView(action_group=group, issues=views)
                for group, views in grouped.items()
            ],
            history=history,
        )
