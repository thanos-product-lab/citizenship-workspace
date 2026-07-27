"""Persistence access for cases and memberships, exposed as domain intent.

Methods name what the domain wants (`list_for_owner`, `is_active_member`), not
generic CRUD. Nothing here decides authorisation — that is the service/dependency
layer's job; the repository only answers questions.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.domain import ApplicationCase, CaseMembership, LifecycleStatus


class CaseRepository:
    @staticmethod
    def get(session: Session, case_id: uuid.UUID) -> ApplicationCase | None:
        return session.get(ApplicationCase, case_id)

    @staticmethod
    def get_for_update(session: Session, case_id: uuid.UUID) -> ApplicationCase | None:
        """Row-locking read (`SELECT … FOR UPDATE`). A write command locks the case
        so a concurrent deletion cannot flip its lifecycle mid-write (ADR-0005 R2).

        `populate_existing` is essential: `require_case_access` already loaded the
        case into the identity map, so without it the locked SELECT returns the
        cached instance with its *stale* lifecycle and the re-check is meaningless.
        This forces the returned instance's columns to refresh from the locked row."""
        stmt = (
            select(ApplicationCase)
            .where(ApplicationCase.id == case_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return session.scalar(stmt)

    @staticmethod
    def add(session: Session, case: ApplicationCase) -> None:
        session.add(case)

    @staticmethod
    def list_for_owner(session: Session, owner_user_id: str) -> list[ApplicationCase]:
        # Exclude DELETED, mirroring the get_case guard: a deleted case is never
        # listed either, even before the purge worker removes the row (ADR-0005).
        stmt = (
            select(ApplicationCase)
            .where(
                ApplicationCase.owner_user_id == owner_user_id,
                ApplicationCase._lifecycle_status != LifecycleStatus.DELETED.value,
            )
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
