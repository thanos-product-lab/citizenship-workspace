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

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.residence.csv_import import ParsedImport, parse_import
from app.residence.domain import (
    EntrySource,
    ProposedApplicationDate,
    ProposedApplicationDateChanged,
    ProposedApplicationDateSelected,
    ProposedApplicationDateVersion,
    TravelLifecycleStatus,
    TravelRecord,
    TravelRecordCreated,
    TravelRecordFields,
    TravelRecordRemoved,
    TravelRecordVersion,
    TravelRecordVersionCreated,
)
from app.residence.repository import (
    ProposedApplicationDateRepository,
    TravelRecordRepository,
)
from app.shared.errors import (
    CaseNotActive,
    ConcurrencyConflict,
    CsvImportInvalid,
    IllegalTransition,
    TravelRecordNotFound,
)
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


# --- Travel records --------------------------------------------------------


@dataclass(frozen=True)
class TravelRecordOutcome:
    record: TravelRecord
    version: TravelRecordVersion


def list_travel_records(session: Session, *, case: ApplicationCase) -> list[TravelRecordOutcome]:
    """Active travel records with their current version, chronological (MVP §8.4)."""
    return [
        TravelRecordOutcome(record=record, version=version)
        for record, version in TravelRecordRepository.list_active_with_current_version(
            session, case.id
        )
    ]


def add_travel_record(
    session: Session, *, case: ApplicationCase, user: CurrentUser, fields: TravelRecordFields
) -> TravelRecordOutcome:
    _require_active_writable_case(session, case)

    record = TravelRecord.start(case_id=case.id)
    TravelRecordRepository.add_record(session, record)
    session.flush()
    version = _build_version(
        record_id=record.id,
        fields=fields,
        version_number=1,
        created_by=user.user_id,
        entry_source=EntrySource.MANUAL,
    )
    TravelRecordRepository.add_version(session, version)
    _advance_record(record, version)

    _emit_travel(
        session,
        user,
        case_id=case.id,
        event=TravelRecordCreated(
            aggregate_id=record.id,
            version_number=version.version_number,
            date_confidence=version.date_confidence,
            review_state=version.review_state,
            entry_source=version.entry_source,
        ),
        action="residence.travel_record_created",
        target_id=version.id,
    )
    session.refresh(record)
    return TravelRecordOutcome(record=record, version=version)


def edit_travel_record(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    travel_record_id: uuid.UUID,
    fields: TravelRecordFields,
    expected_revision: int | None,
) -> TravelRecordOutcome:
    _require_active_writable_case(session, case)
    record = _load_record_in_case(session, case, travel_record_id)
    if record.lifecycle_status is not TravelLifecycleStatus.ACTIVE:
        raise IllegalTransition("cannot edit a removed travel record")
    _check_record_revision(record, expected_revision)

    current = (
        TravelRecordRepository.get_version(session, record.current_version_id)
        if record.current_version_id is not None
        else None
    )
    version = _build_version(
        record_id=record.id,
        fields=fields,
        version_number=(current.version_number + 1) if current else 1,
        created_by=user.user_id,
        entry_source=EntrySource.MANUAL,
        supersedes_version_id=current.id if current else None,
    )
    TravelRecordRepository.add_version(session, version)
    _advance_record(record, version)

    _emit_travel(
        session,
        user,
        case_id=case.id,
        event=TravelRecordVersionCreated(
            aggregate_id=record.id,
            version_number=version.version_number,
            date_confidence=version.date_confidence,
            review_state=version.review_state,
            entry_source=version.entry_source,
        ),
        action="residence.travel_record_edited",
        target_id=version.id,
    )
    session.refresh(record)
    return TravelRecordOutcome(record=record, version=version)


def remove_travel_record(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    travel_record_id: uuid.UUID,
    expected_revision: int | None,
) -> TravelRecordOutcome:
    _require_active_writable_case(session, case)
    record = _load_record_in_case(session, case, travel_record_id)
    _check_record_revision(record, expected_revision)
    record.mark_removed()  # ACTIVE → REMOVED; raises if already removed (idempotency)

    _emit_travel(
        session,
        user,
        case_id=case.id,
        event=TravelRecordRemoved(aggregate_id=record.id),
        action="residence.travel_record_removed",
        target_id=record.id,
    )
    session.refresh(record)
    # The record keeps pointing at its last version so the tombstone stays inspectable.
    assert record.current_version_id is not None  # a removed record retains its final version
    version = TravelRecordRepository.get_version(session, record.current_version_id)
    assert version is not None
    return TravelRecordOutcome(record=record, version=version)


def validate_csv_import(session: Session, *, case: ApplicationCase, content: str) -> ParsedImport:
    """Dry-run: parse and validate the CSV, write nothing. Read-only, so it is not gated
    on ACTIVE — validating before a case is active is legitimate; only the commit writes."""
    return parse_import(content)


def import_travel_records(
    session: Session, *, case: ApplicationCase, user: CurrentUser, content: str
) -> list[TravelRecordOutcome]:
    """Commit an import atomically: if any row is invalid, reject the whole batch and
    write nothing; otherwise create one CSV_IMPORT record (v1) per row in a single
    transaction. Re-importing is not deduplicated here — duplicate detection is the M3B
    consistency rule's job, and set-union absence counting makes it idempotent anyway."""
    _require_active_writable_case(session, case)
    parsed = parse_import(content)
    if not parsed.all_valid:
        # Local import: the boundary schema builds the 422 payload (every row, so the
        # user can fix and retry). Kept function-local so the service module does not
        # depend on the schema layer at import time.
        from app.residence.schemas import ImportValidationResponse

        raise CsvImportInvalid(ImportValidationResponse.from_parsed(parsed).model_dump(mode="json"))

    outcomes: list[TravelRecordOutcome] = []
    uow = UnitOfWork(session, actor_id=user.user_id)
    for fields in parsed.valid_fields:
        record = TravelRecord.start(case_id=case.id)
        TravelRecordRepository.add_record(session, record)
        session.flush()
        version = _build_version(
            record_id=record.id,
            fields=fields,
            version_number=1,
            created_by=user.user_id,
            entry_source=EntrySource.CSV_IMPORT,
        )
        TravelRecordRepository.add_version(session, version)
        _advance_record(record, version)
        uow.emit(
            TravelRecordCreated(
                aggregate_id=record.id,
                version_number=version.version_number,
                date_confidence=version.date_confidence,
                review_state=version.review_state,
                entry_source=version.entry_source,
            ),
            case_id=case.id,
            action="residence.travel_record_imported",
            target_type="TravelRecord",
            target_id=version.id,
        )
        outcomes.append(TravelRecordOutcome(record=record, version=version))
    uow.commit()
    for outcome in outcomes:
        session.refresh(outcome.record)
    return outcomes


def _build_version(
    *,
    record_id: uuid.UUID,
    fields: TravelRecordFields,
    version_number: int,
    created_by: str,
    entry_source: EntrySource,
    supersedes_version_id: uuid.UUID | None = None,
) -> TravelRecordVersion:
    # entry_source is required (never defaulted): provenance must be stated by the
    # caller, not silently assumed MANUAL. Manual create/edit pass MANUAL; import CSV_IMPORT.
    return TravelRecordVersion.build(
        travel_record_id=record_id,
        version_number=version_number,
        destination_label=fields.destination_label,
        departure_date=fields.departure_date,
        return_date=fields.return_date,
        date_confidence=fields.date_confidence,
        review_state=fields.review_state,
        entry_source=entry_source,
        created_by=created_by,
        destination_country_code=fields.destination_country_code,
        notes=fields.notes,
        supersedes_version_id=supersedes_version_id,
    )


def _emit_travel(
    session: Session,
    user: CurrentUser,
    *,
    case_id: uuid.UUID,
    event: DomainEvent,
    action: str,
    target_id: uuid.UUID,
) -> None:
    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        event,
        case_id=case_id,
        action=action,
        target_type="TravelRecord",
        target_id=target_id,
    )
    uow.commit()


def _load_record_in_case(
    session: Session, case: ApplicationCase, travel_record_id: uuid.UUID
) -> TravelRecord:
    """The record, only if it belongs to this case. RLS hides other tenants, but not
    the caller's other cases, so the case link is checked here (Domain §3.1)."""
    record = TravelRecordRepository.get(session, travel_record_id)
    if record is None or record.case_id != case.id:
        raise TravelRecordNotFound()
    return record


def _advance_record(record: TravelRecord, version: TravelRecordVersion) -> None:
    record.current_version_id = version.id
    flag_modified(record, "current_version_id")


def _check_record_revision(record: TravelRecord, expected: int | None) -> None:
    if expected is not None and expected != record.revision:
        raise ConcurrencyConflict()
