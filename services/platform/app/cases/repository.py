"""Persistence access for cases and memberships, exposed as domain intent.

Methods name what the domain wants (`list_for_owner`, `is_active_member`), not
generic CRUD. Nothing here decides authorisation — that is the service/dependency
layer's job; the repository only answers questions.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.domain import ApplicationCase, CaseMembership


class CaseRepository:
    @staticmethod
    def get(session: Session, case_id: uuid.UUID) -> ApplicationCase | None:
        return session.get(ApplicationCase, case_id)

    @staticmethod
    def get_for_update(session: Session, case_id: uuid.UUID) -> ApplicationCase | None:
        """Row-locking read (`SELECT … FOR UPDATE`). A write command locks the case
        so a concurrent deletion cannot flip its lifecycle mid-write (ADR-0005 R2)."""
        stmt = select(ApplicationCase).where(ApplicationCase.id == case_id).with_for_update()
        return session.scalar(stmt)

    @staticmethod
    def add(session: Session, case: ApplicationCase) -> None:
        session.add(case)

    @staticmethod
    def list_for_owner(session: Session, owner_user_id: str) -> list[ApplicationCase]:
        stmt = (
            select(ApplicationCase)
            .where(ApplicationCase.owner_user_id == owner_user_id)
            .order_by(ApplicationCase.created_at.desc())
        )
        return list(session.scalars(stmt))


class MembershipRepository:
    @staticmethod
    def add(session: Session, membership: CaseMembership) -> None:
        session.add(membership)

    @staticmethod
    def is_active_member(session: Session, case_id: uuid.UUID, user_id: str) -> bool:
        stmt = select(CaseMembership.id).where(
            CaseMembership.case_id == case_id,
            CaseMembership.user_id == user_id,
            CaseMembership.revoked_at.is_(None),
        )
        return session.scalar(stmt) is not None
