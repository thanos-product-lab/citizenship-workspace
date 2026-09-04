"""Reads over `extraction_runs`. Domain intent, never generic CRUD.

There is no `update` and no `delete` here, and that is the point: a run is written once
when its outcome is known (RFC §17 — reprocessing creates a *new* run, it does not
rewrite the old one), so a repository that offered a way to change one would be offering
a way to rewrite what the system used to think about a document.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.domain import Capability
from app.ai.extraction_run import ExtractionRun
from app.cases.domain import ApplicationCase


class ExtractionRunRepository:
    @staticmethod
    def calls_today(session: Session, *, case_id: uuid.UUID, at: datetime) -> int:
        """How many capability invocations this case has made in the last 24 hours.

        Counts *every* run including the refusals, which is deliberate: a loop that keeps
        being refused is still a loop, and a counter that only saw the successful calls
        would reset itself the moment the quota started working.
        """
        return int(
            session.execute(
                select(func.count())
                .select_from(ExtractionRun)
                .where(
                    ExtractionRun.case_id == case_id,
                    ExtractionRun.started_at > at - timedelta(days=1),
                )
            ).scalar_one()
        )

    @staticmethod
    def calls_today_for_the_owner_of(session: Session, *, case_id: uuid.UUID, at: datetime) -> int:
        """How many invocations the owner of this case has made across *all* their cases.

        Keyed off the case rather than taking an owner id, so the quota needs no new
        parameter threaded from the worker down through the pipeline — `case_id` is
        already in hand everywhere a capability is invoked, and the join is the same one
        the row-level policy already makes.

        Joined explicitly rather than relying on the session's tenant to scope it. RLS
        would in fact produce the same number, and that is exactly why it should not be
        the mechanism: a business limit that silently becomes "no limit" the day
        something runs as the table owner is not a limit.
        """
        return int(
            session.execute(
                select(func.count())
                .select_from(ExtractionRun)
                .join(ApplicationCase, ApplicationCase.id == ExtractionRun.case_id)
                .where(
                    ApplicationCase.owner_user_id.in_(
                        select(ApplicationCase.owner_user_id).where(ApplicationCase.id == case_id)
                    ),
                    ExtractionRun.started_at > at - timedelta(days=1),
                )
            ).scalar_one()
        )

    @staticmethod
    def latest_classification(
        session: Session, *, evidence_item_id: uuid.UUID
    ) -> ExtractionRun | None:
        """The most recent classification of one document.

        Most recent rather than "the successful one": a document reprocessed after a
        failed analysis should show the *current* answer, and a stale success sitting in
        front of a fresh failure would tell a user the analysis worked when the last
        thing that happened was that it did not.
        """
        return session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.evidence_item_id == evidence_item_id,
                ExtractionRun.capability == Capability.DOCUMENT_CLASSIFIER.value,
            )
            .order_by(ExtractionRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def latest_classifications_for_case(
        session: Session, *, case_id: uuid.UUID
    ) -> dict[uuid.UUID, ExtractionRun]:
        """One row per evidence item, newest first, for the library listing.

        Fetched in one query rather than per item: the library renders every document in
        a case, and a per-row read is the N+1 that turns a page load into a hundred
        round trips.
        """
        rows = session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.case_id == case_id,
                ExtractionRun.capability == Capability.DOCUMENT_CLASSIFIER.value,
            )
            .order_by(ExtractionRun.started_at.desc())
        ).scalars()
        latest: dict[uuid.UUID, ExtractionRun] = {}
        for run in rows:
            latest.setdefault(run.evidence_item_id, run)
        return latest
