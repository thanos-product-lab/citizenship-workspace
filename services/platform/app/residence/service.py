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
from types import EllipsisType

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.assessments.invalidation import StaleReason, invalidate_for_input_change
from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, LifecycleStatus

# The link *module*, not the evidence service: it reads the travel repository and never
# this file, so the dependency between the two modules runs one way only.
from app.evidence import links
from app.evidence.domain import utcnow
from app.requirements.models import DependencyInputKind
from app.residence.csv_import import ParsedImport, parse_import
from app.residence.domain import (
    DateConfidence,
    EntrySource,
    ProposedApplicationDate,
    ProposedApplicationDateChanged,
    ProposedApplicationDateSelected,
    ProposedApplicationDateVersion,
    TravelLifecycleStatus,
    TravelRecord,
    TravelRecordCreated,
    TravelRecordFields,
    TravelRecordReasonChanged,
    TravelRecordRemoved,
    TravelRecordVersion,
    TravelRecordVersionCreated,
    TravelReviewState,
    counts_toward_trusted_total,
    version_matches,
)
from app.residence.export import ExportScope, ExportTripInput, TravelExport, build_export
from app.residence.repository import (
    ProposedApplicationDateRepository,
    TravelRecordRepository,
)
from app.shared.errors import (
    ApplicationDateInPast,
    CaseNotActive,
    ConcurrencyConflict,
    CsvImportInvalid,
    IllegalTransition,
    NoConflictToResolve,
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


def _require_not_already_past(application_date: date) -> None:
    """Refuse a date that had already passed when it was chosen.

    **Read `ApplicationDateInPast` before moving this.** It belongs to the command and
    not to `residence/schemas.py`, whose docstring declines a future/past constraint at
    the input boundary for a reason that still holds: a type-level rule would refuse to
    read back a case nobody touched, purely because a calendar boundary went by. This
    only ever fires on a date somebody is choosing right now.

    Today is allowed. Applying today is a real intention, and the qualifying period it
    measures ends today rather than in a window that has closed.

    The clock is read here rather than anywhere further in, because everything below
    `requirements/` is a pure function of its inputs by design — no evaluator reads a
    clock, which is what makes a result reproducible from its recorded input versions.
    """
    today = utcnow().date()
    if application_date < today:
        raise ApplicationDateInPast(application_date, today)


def select_application_date(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    application_date: date,
    expected_revision: int | None,
) -> ApplicationDateOutcome:
    _require_active_writable_case(session, case)
    _require_not_already_past(application_date)

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
    # Selective stale propagation in the same transaction (§41.2). The date reaches further
    # than residence — `status.holding_period` and, through the composite, the route rules
    # declare it too — so the affected set is resolved from the declarations, not from this
    # module's idea of which requirements care. No-op on the first selection.
    invalidate_for_input_change(
        session,
        uow,
        case_id=case.id,
        input_kind=DependencyInputKind.PROPOSED_APPLICATION_DATE,
        reason_code=StaleReason.APPLICATION_DATE_CHANGED,
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
    """One travel record, with the §6.1 trust decision already made.

    `is_trusted` is carried rather than left to the caller, and that is the whole point of
    this type. The web client used to compute `review_state === "CONFIRMED" &&
    date_confidence === "EXACT"` for itself, which was correct until a confirmed document
    date could dispute a trip — the stored row still reads EXACT/CONFIRMED, because the
    conflict is derived and never written (RFC §42), so the client showed a held-back trip
    as plainly "Confirmed" on the very page where the document was attached (ADR-0028).

    A caller given the ingredients will eventually recombine them. This gives the answer.
    """

    record: TravelRecord
    version: TravelRecordVersion
    #: The §6.1 gate: ACTIVE + CONFIRMED + EXACT, **and** undisputed.
    is_trusted: bool
    #: Held back because a confirmed document date disagrees with it, rather than because
    #: it was never confirmed. Published separately because the two take different
    #: remedies, and `date_confidence` cannot say it — that field is the value the *user*
    #: entered, and it has to stay that way or the edit form would offer a state they
    #: never chose.
    is_disputed_by_document: bool

    @classmethod
    def of(
        cls,
        record: TravelRecord,
        version: TravelRecordVersion,
        disputed: frozenset[uuid.UUID] = frozenset(),
    ) -> "TravelRecordOutcome":
        return cls(
            record=record,
            version=version,
            is_trusted=counts_toward_trusted_total(record, version) and record.id not in disputed,
            is_disputed_by_document=record.id in disputed,
        )


def disputed_record_ids(session: Session, *, case_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """Trips a confirmed document date disagrees with, from the assessment's own detector.

    Imported lazily for the reason `_documented_dates_for` does it: `assessments.service`
    imports this module, and the detection has to be the same one the assessment runs or
    the two surfaces are free to disagree again — which is the defect this exists to close.
    """
    from app.assessments.conflicts import conflicted_record_ids
    from app.assessments.service import detect_case_conflicts

    return conflicted_record_ids(detect_case_conflicts(session, case_id))


def list_travel_records(session: Session, *, case: ApplicationCase) -> list[TravelRecordOutcome]:
    """Active travel records with their current version, chronological (MVP §8.4)."""
    disputed = disputed_record_ids(session, case_id=case.id)
    return [
        TravelRecordOutcome.of(record, version, disputed)
        for record, version in TravelRecordRepository.list_active_with_current_version(
            session, case.id
        )
    ]


def add_travel_record(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    fields: TravelRecordFields,
    reason: str | None = None,
) -> TravelRecordOutcome:
    _require_active_writable_case(session, case)

    record = TravelRecord.start(case_id=case.id)
    # Set before the first flush, as part of creating the trip: a reason given on creation
    # is covered by the created event and needs no audit entry of its own.
    record.set_reason(reason)
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
    return TravelRecordOutcome.of(record, version, disputed_record_ids(session, case_id=case.id))


def edit_travel_record(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    travel_record_id: uuid.UUID,
    fields: TravelRecordFields,
    expected_revision: int | None,
    reason: str | EllipsisType | None = ...,
) -> TravelRecordOutcome:
    """Save the trip form: a new version when a version field changed, and the reason.

    **An edit that changes no version field appends no version and stales nothing**
    (ADR-0035). The reason is not on the version, so typing one in, or saving the form
    unchanged, used to be (or would have been) a new version and eight stale conclusions
    over a trip whose dates never moved. Anything a rule reads is on the version, so "no
    version field changed" is exactly "nothing an assessment depends on changed": the
    results stay current because they are still true, not because a check was skipped.

    `reason=...` (omitted) keeps the reason; `None` or blank clears it. The edit is a whole
    snapshot of the version, but a client that predates the reason must not erase one.
    """
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
    uow = UnitOfWork(session, actor_id=user.user_id)

    if current is not None and version_matches(current, fields):
        if not isinstance(reason, EllipsisType) and record.set_reason(reason):
            uow.emit(
                TravelRecordReasonChanged(aggregate_id=record.id),
                case_id=case.id,
                action="residence.travel_record_reason_changed",
                target_type="TravelRecord",
                target_id=record.id,
            )
            uow.commit()
            session.refresh(record)
        return TravelRecordOutcome.of(
            record, current, disputed_record_ids(session, case_id=case.id)
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
    reason_changed = not isinstance(reason, EllipsisType) and record.set_reason(reason)

    uow.emit(
        TravelRecordVersionCreated(
            aggregate_id=record.id,
            version_number=version.version_number,
            date_confidence=version.date_confidence,
            review_state=version.review_state,
            entry_source=version.entry_source,
        ),
        case_id=case.id,
        action="residence.travel_record_edited",
        target_type="TravelRecord",
        target_id=version.id,
    )
    if reason_changed:
        uow.emit(
            TravelRecordReasonChanged(aggregate_id=record.id),
            case_id=case.id,
            action="residence.travel_record_reason_changed",
            target_type="TravelRecord",
            target_id=record.id,
        )
    # A version field changed, so the rules declaring a travel dependency are stale, in
    # the same transaction (§41.2).
    invalidate_for_input_change(
        session,
        uow,
        case_id=case.id,
        input_kind=DependencyInputKind.TRAVEL_RECORD,
        reason_code=StaleReason.TRAVEL_RECORD_CHANGED,
    )
    uow.commit()
    session.refresh(record)
    return TravelRecordOutcome.of(record, version, disputed_record_ids(session, case_id=case.id))


def adopt_document_dates(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    travel_record_id: uuid.UUID,
    expected_revision: int | None,
) -> TravelRecordOutcome:
    """Resolve a conflict in the document's favour: take its dates as the trip's.

    **One new version carrying every conflicting date**, not one per field. A booking whose
    departure and return both disagree is one decision the user made, and two versions
    would make the history read as two — with a state in between where half the document
    had been adopted and the trip agreed with neither source.

    `entry_source = CONFIRMED_CLAIM`, which is the first producer that enum member has had.
    It is what lets a later reader tell a date the user typed from a date they took off a
    document they had already confirmed — the same distinction `CSV_IMPORT` exists for.

    `date_confidence = EXACT` and `review_state = CONFIRMED`: the value came from a
    document the user read and confirmed, so it is as established as anything they typed.
    The conflict disappears because the two sources now agree, not because it was dismissed.

    **Refuses when nothing is in conflict** (409). An action that silently does nothing is
    how a user comes to believe they resolved something — and this one is reachable from a
    queue that may be a few seconds stale.

    **No `expected_revision`, unlike every other travel command**, and that is a decision
    rather than an omission. The others edit a value the client read, so a revision token
    is what stops them overwriting an edit made since. This one asks the server to resolve
    a disagreement the *server* determined: the client sends no dates, and the conflict is
    re-detected here, so there is no stale client view for a token to protect against.

    Concurrency is handled a layer up instead. `_require_active_writable_case` takes the
    case row lock for the transaction (ADR-0005 R2), so two adoptions — or an adoption
    racing an edit — serialise. The second one re-detects, finds the two sources now agree,
    and gets the 409 above rather than writing a second identical version.

    Goes through `_emit_travel`, so dependants are staled in this transaction by the path
    every other travel write already uses. No new staleness mechanism, and none wanted:
    what changed *is* a travel record.
    """
    _require_active_writable_case(session, case)
    record = _load_record_in_case(session, case, travel_record_id)
    if record.lifecycle_status is not TravelLifecycleStatus.ACTIVE:
        raise IllegalTransition("cannot change a removed travel record")
    _check_record_revision(record, expected_revision)

    current = (
        TravelRecordRepository.get_version(session, record.current_version_id)
        if record.current_version_id is not None
        else None
    )
    if current is None:  # pragma: no cover - an active record always has a version
        raise IllegalTransition("this trip has no dates to change")

    documented = _documented_dates_for(session, case, record.id)
    if not documented:
        raise NoConflictToResolve()

    fields = TravelRecordFields(
        destination_label=current.destination_label,
        departure_date=documented.get("departure_date", current.departure_date),
        return_date=documented.get("return_date", current.return_date),
        date_confidence=DateConfidence.EXACT,
        review_state=TravelReviewState.CONFIRMED,
        destination_country_code=current.destination_country_code,
        notes=current.notes,
    )
    version = _build_version(
        record_id=record.id,
        fields=fields,
        version_number=current.version_number + 1,
        created_by=user.user_id,
        entry_source=EntrySource.CONFIRMED_CLAIM,
        supersedes_version_id=current.id,
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
        action="residence.document_dates_adopted",
        target_id=version.id,
    )
    session.refresh(record)
    return TravelRecordOutcome.of(record, version, disputed_record_ids(session, case_id=case.id))


def _documented_dates_for(
    session: Session, case: ApplicationCase, travel_record_id: uuid.UUID
) -> dict[str, date]:
    """The confirmed document dates that disagree with this trip, by field.

    Detection is `assessments.conflicts` — the same pure comparison the assessment runs, not
    a second implementation of it. Two implementations would be free to disagree, and the
    one place that must never happen is between what the queue offers to resolve and what
    the assessment thinks is in conflict.
    """
    from app.assessments.service import detect_case_conflicts

    return {
        conflict.field: conflict.documented
        for conflict in detect_case_conflicts(session, case.id)
        if conflict.travel_record_id == travel_record_id
    }


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

    # This command builds its own unit of work rather than using `_emit_travel`, because
    # it changes two aggregates: the record, and any evidence links attached to it. Both
    # have to land in one transaction — a removal that committed without withdrawing the
    # links would leave a removed trip holding live support, and the reverse order would
    # withdraw support from a trip that still exists.
    uow = UnitOfWork(session, actor_id=user.user_id)
    links.withdraw_links_for_travel_record(
        session, uow, case_id=case.id, travel_record_id=record.id, at=utcnow()
    )
    uow.emit(
        TravelRecordRemoved(aggregate_id=record.id),
        case_id=case.id,
        action="residence.travel_record_removed",
        target_type="TravelRecord",
        target_id=record.id,
    )
    invalidate_for_input_change(
        session,
        uow,
        case_id=case.id,
        input_kind=DependencyInputKind.TRAVEL_RECORD,
        reason_code=StaleReason.TRAVEL_RECORD_CHANGED,
    )
    uow.commit()
    session.refresh(record)
    # The record keeps pointing at its last version so the tombstone stays inspectable.
    assert record.current_version_id is not None  # a removed record retains its final version
    version = TravelRecordRepository.get_version(session, record.current_version_id)
    assert version is not None
    return TravelRecordOutcome.of(record, version, disputed_record_ids(session, case_id=case.id))


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
    # Imported rows are new, so none can be disputed — nothing is attached to them yet.
    # Read once anyway rather than passing an empty set: a hardcoded "cannot be disputed"
    # is a claim that goes stale the moment import learns to attach a document, and it
    # would go stale silently.
    disputed = disputed_record_ids(session, case_id=case.id)
    uow = UnitOfWork(session, actor_id=user.user_id)
    for fields, reason in parsed.valid_rows:
        record = TravelRecord.start(case_id=case.id)
        record.set_reason(reason)
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
        outcomes.append(TravelRecordOutcome.of(record, version, disputed))
    # One invalidation for the whole batch, not one per row: the affected set is identical
    # for every travel write, and staling a result twice would only reset its reason code.
    invalidate_for_input_change(
        session,
        uow,
        case_id=case.id,
        input_kind=DependencyInputKind.TRAVEL_RECORD,
        reason_code=StaleReason.TRAVEL_RECORD_CHANGED,
    )
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
    # Any travel change restales the rules declaring a travel dependency, in the same
    # transaction (§41.2). `residence.qualifying_period` declares none — it reads only the
    # application date — so it is correctly left alone.
    invalidate_for_input_change(
        session,
        uow,
        case_id=case_id,
        input_kind=DependencyInputKind.TRAVEL_RECORD,
        reason_code=StaleReason.TRAVEL_RECORD_CHANGED,
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


# --- Travel export (ADR-0035) ---------------------------------------------------------


def get_travel_export(
    session: Session, *, case: ApplicationCase, scope: ExportScope, today: date
) -> TravelExport:
    """The trips as a list to hand over, with the same trust overlay the assessment uses.

    Trips come from `gather_trips`, so a trip a confirmed document disputes is marked here
    exactly when the assessment holds it back (ADR-0028). Imported lazily for the cycle
    `disputed_record_ids` describes.
    """
    from app.assessments.service import gather_trips
    from app.evidence.domain import EvidenceProcessingStatus
    from app.evidence.repository import EvidenceRepository

    gathered, _conflicts = gather_trips(session, case.id)
    reasons = {
        record.id: record.reason
        for record, _version in TravelRecordRepository.list_active_with_current_version(
            session, case.id
        )
    }
    current = get_current(session, case=case)
    awaiting = sum(
        1
        for item, _file in EvidenceRepository.list_uploaded_for_case(session, case_id=case.id)
        if item.processing_status == EvidenceProcessingStatus.AWAITING_CONFIRMATION.value
    )
    return build_export(
        trips=[
            ExportTripInput(
                travel_record_id=trip.travel_record_id,
                destination_label=trip.destination_label,
                reason=reasons.get(trip.travel_record_id),
                departure_date=trip.departure_date,
                return_date=trip.return_date,
                review_state=trip.review_state,
                date_confidence=trip.date_confidence,
            )
            for trip in gathered
        ],
        application_date=current.version.application_date if current else None,
        scope=scope,
        documents_awaiting_review=awaiting,
        prepared_on=today,
    )
