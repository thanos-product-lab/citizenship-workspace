"""Persistence for the issue queue. Domain intent, not generic CRUD.

Reads are keyed by *cause* (`deduplication_key`) rather than by id, because that is how
reconciliation thinks: it holds a desired set of causes and needs to know which already
have a live row.
"""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.issues.domain import LIVE_STATUSES, Issue, IssueResolution, IssueStatus, ResolutionType


class IssueRepository:
    @staticmethod
    def add(session: Session, issue: Issue) -> None:
        session.add(issue)

    @staticmethod
    def get(session: Session, case_id: uuid.UUID, issue_id: uuid.UUID) -> Issue | None:
        return session.scalar(
            select(Issue).where(Issue.id == issue_id, Issue.case_id == case_id)
        )

    @staticmethod
    def list_live(session: Session, case_id: uuid.UUID) -> list[Issue]:
        """Every issue still representing a cause — OPEN, IN_PROGRESS or DISMISSED. This is
        the set reconciliation diffs against, so it must include DISMISSED: a dismissed
        issue is not recreated while its cause persists."""
        return list(
            session.scalars(
                select(Issue)
                .where(Issue.case_id == case_id, Issue.status.in_(LIVE_STATUSES))
                .order_by(Issue.opened_at)
            )
        )

    @staticmethod
    def get_by_deduplication_key(session: Session, case_id: uuid.UUID, key: str) -> Issue | None:
        """The most recent issue for a cause, live or resolved. Ordered newest-first so a
        cause that has recurred several times reopens its latest episode."""
        return session.scalar(
            select(Issue)
            .where(Issue.case_id == case_id, Issue.deduplication_key == key)
            .order_by(Issue.opened_at.desc())
        )

    @staticmethod
    def list_for_case(session: Session, case_id: uuid.UUID) -> list[Issue]:
        """Every issue ever raised for the case, newest first — the queue plus its history."""
        return list(
            session.scalars(
                select(Issue).where(Issue.case_id == case_id).order_by(Issue.opened_at.desc())
            )
        )

    @staticmethod
    def count_open(session: Session, case_id: uuid.UUID) -> int:
        """Issues awaiting the user: OPEN or IN_PROGRESS. Dismissed ones are excluded — the
        user has already decided about them, and counting them would make the badge
        un-clearable."""
        return len(
            list(
                session.scalars(
                    select(Issue.id).where(
                        Issue.case_id == case_id,
                        Issue.status.in_((IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value)),
                    )
                )
            )
        )

    @staticmethod
    def list_resolutions(
        session: Session, issue_ids: Collection[uuid.UUID]
    ) -> list[IssueResolution]:
        if not issue_ids:
            return []
        return list(
            session.scalars(
                select(IssueResolution)
                .where(IssueResolution.issue_id.in_(tuple(issue_ids)))
                .order_by(IssueResolution.resolved_at.desc())
            )
        )

    @staticmethod
    def record_resolution(
        session: Session,
        *,
        issue_id: uuid.UUID,
        resolution_type: ResolutionType,
        resolved_by: str,
        at: datetime,
        notes: str | None = None,
    ) -> IssueResolution:
        resolution = IssueResolution(
            id=uuid.uuid4(),
            issue_id=issue_id,
            resolution_type=resolution_type.value,
            resolved_by=resolved_by,
            resolved_at=at,
            notes=notes,
            resulting_object_ids=[],
        )
        session.add(resolution)
        return resolution
