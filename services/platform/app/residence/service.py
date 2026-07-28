"""Residence commands. Domain logic lives here, not in the route handlers.

Slice 1 command: `select_application_date`. Selecting the first date creates the
case's ProposedApplicationDate root and its version 1 and points the case at it;
selecting again appends a new immutable CONFIRMED version to the same root (the date
evolves). State + event (`Selected`/`Changed`) + audit + outbox commit atomically.

Every residence write is gated on the case being ACTIVE (`_require_active_writable_case`):
residence inputs exist only to be assessed, and a case is assessable only once
onboarding resolves to a supported route (the M2 ACTIVE signal). A non-active case
raises `CaseNotActive` (→ 409 with a code), never a 404 — the case is real and owned,
it is just not ready, and the user needs to understand that rather than have it hidden.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.residence.domain import (
    ProposedApplicationDate,
    ProposedApplicationDateChanged,
    ProposedApplicationDateSelected,
    ProposedApplicationDateVersion,
)
from app.residence.repository import ProposedApplicationDateRepository
from app.shared.errors import CaseNotActive, ConcurrencyConflict
from app.shared.messaging import DomainEvent
from app.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class ApplicationDateOutcome:
    root: ProposedApplicationDate
    version: ProposedApplicationDateVersion


def get_current(session: Session, *, case: ApplicationCase) -> ApplicationDateOutcome | None:
    """The case's current proposed date and its current version, or None if unset."""
    root = ProposedApplicationDateRepository.get_current_for_case(session, case.id)
    if root is None or root.current_version_id is None:
        return None
    version = ProposedApplicationDateRepository.get_version(session, root.current_version_id)
    if version is None:
        return None
    return ApplicationDateOutcome(root=root, version=version)


def select_application_date(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    application_date: date,
    expected_revision: int | None,
) -> ApplicationDateOutcome:
    _require_active_writable_case(session, case)

    root = ProposedApplicationDateRepository.get_current_for_case(session, case.id)
    event: DomainEvent
    if root is None:
        # First selection: create the root, its version 1, and point the case at it.
        root = ProposedApplicationDate.start(case_id=case.id)
        ProposedApplicationDateRepository.add_root(session, root)
        session.flush()
        version = ProposedApplicationDateVersion.new_confirmed(
            proposed_application_date_id=root.id,
            application_date=application_date,
            created_by=user.user_id,
            version_number=1,
        )
        ProposedApplicationDateRepository.add_version(session, version)
        _advance_root(root, version)
        case.set_current_application_date(root.id)  # authoritative pointer (§10.3)
        event = ProposedApplicationDateSelected(
            aggregate_id=root.id,
            version_number=version.version_number,
            application_date=application_date.isoformat(),
            source=version.source,
        )
    else:
        # Change the current date: append a new immutable version (never edit in place).
        _check_revision(root, expected_revision)
        current = (
            ProposedApplicationDateRepository.get_version(session, root.current_version_id)
            if root.current_version_id is not None
            else None
        )
        version = ProposedApplicationDateVersion.new_confirmed(
            proposed_application_date_id=root.id,
            application_date=application_date,
            created_by=user.user_id,
            version_number=(current.version_number + 1) if current else 1,
            supersedes_version_id=current.id if current else None,
        )
        ProposedApplicationDateRepository.add_version(session, version)
        _advance_root(root, version)
        # Case pointer already targets this root; the case is not mutated on a change.
        event = ProposedApplicationDateChanged(
            aggregate_id=root.id,
            version_number=version.version_number,
            application_date=application_date.isoformat(),
            source=version.source,
        )

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        event,
        case_id=case.id,
        action="residence.application_date_selected",
        target_type="ProposedApplicationDateVersion",
        target_id=version.id,
    )
    uow.commit()
    session.refresh(root)
    return ApplicationDateOutcome(root=root, version=version)


# --- helpers ---------------------------------------------------------------


def _require_active_writable_case(session: Session, case: ApplicationCase) -> None:
    """Lock the case row and confirm it is ACTIVE before any residence write. The lock
    serialises against a concurrent deletion (ADR-0005 R2); a non-ACTIVE case (still
    onboarding, archived, or vanished) raises CaseNotActive rather than a 404."""
    locked = cases_service.lock_writable_case(session, case.id)
    status = locked.lifecycle_status if locked is not None else case.lifecycle_status
    if status is not LifecycleStatus.ACTIVE:
        raise CaseNotActive(status.value)


def _advance_root(root: ProposedApplicationDate, version: ProposedApplicationDateVersion) -> None:
    # Point at the current version and force the root's concurrency token to advance
    # even though only the child version row carries the new value.
    root.current_version_id = version.id
    flag_modified(root, "current_version_id")


def _check_revision(root: ProposedApplicationDate, expected: int | None) -> None:
    # Fast explicit conflict; version_id_col is the ultimate guard on commit.
    if expected is not None and expected != root.revision:
        raise ConcurrencyConflict()
