"""Persistence access for the proposed application date, exposed as domain intent."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.residence.domain import ProposedApplicationDate, ProposedApplicationDateVersion


class ProposedApplicationDateRepository:
    @staticmethod
    def get_current_for_case(
        session: Session, case_id: uuid.UUID
    ) -> ProposedApplicationDate | None:
        """The case's current proposed-date root (M3A has at most one per case)."""
        return session.scalar(
            select(ProposedApplicationDate).where(
                ProposedApplicationDate.case_id == case_id,
                ProposedApplicationDate.is_current.is_(True),
            )
        )

    @staticmethod
    def get_version(
        session: Session, version_id: uuid.UUID
    ) -> ProposedApplicationDateVersion | None:
        return session.get(ProposedApplicationDateVersion, version_id)

    @staticmethod
    def add_root(session: Session, root: ProposedApplicationDate) -> None:
        session.add(root)

    @staticmethod
    def add_version(session: Session, version: ProposedApplicationDateVersion) -> None:
        session.add(version)
