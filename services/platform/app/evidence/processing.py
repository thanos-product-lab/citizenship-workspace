"""Running the pipeline against one file, and recording what happened.

This is the code a Celery task calls once its tenant context exists. It is here rather
than in `worker/` for the reason CLAUDE.md §6 gives: domain logic lives in the module
that owns the domain, and the worker is a way of invoking it, not a place to keep it.

Three properties this file exists to hold, each of which is a stated invariant rather
than a preference:

**A duplicate delivery produces no second run.** `idempotency_key` is the outbox row's
id and unique, so a redelivery either finds the existing run or loses the insert race —
both return without doing the work again (CLAUDE.md §9).

**A processing failure never deletes the uploaded evidence.** Structural rather than
careful: nothing in this module can delete a stored object. The only code that removes
content is the purge path, reachable only from `EvidenceDeletionRequested`.

**A user is never shown a queue state.** The run's status is the worker's vocabulary;
`PROCESSING_STATUS_FOR_RUN` is the only bridge to the §14.4 states the API can speak,
and it is total over both enums.
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.storage import StorageAdapter, StorageError
from app.evidence import validation
from app.evidence.domain import (
    PROCESSING_STATUS_FOR_RUN,
    EvidenceFile,
    EvidenceItem,
    EvidenceLifecycleStatus,
    EvidenceProcessingRun,
    EvidenceProcessingStatus,
    ProcessingFailureCode,
    ProcessingRunStatus,
    utcnow,
)

_log = structlog.get_logger()


#: Run statuses that mean a verdict was reached. A run in any other state is either
#: this delivery's own attempt in progress or one that died mid-flight — and in both
#: cases the right move is to carry on, not to report the work already done.
SETTLED_RUN_STATUSES = frozenset(
    {
        ProcessingRunStatus.SUCCEEDED,
        ProcessingRunStatus.FAILED,
        ProcessingRunStatus.PARTIAL,
        ProcessingRunStatus.CANCELLED,
    }
)


class EvidenceNotProcessable(Exception):
    """There is nothing here to process: the item is gone, deleted, or has no file.

    A dedicated type rather than `LookupError`, because `KeyError` *is* a `LookupError`
    — so catching the latter in the task turned every dict miss anywhere in the pipeline
    into a silent "evidence absent" success, leaving a real bug looking like a tidy
    cancellation. That gets worse in slice 3, where extraction adds lookups.
    """


class TransientProcessingError(Exception):
    """The store or the network was unavailable. Worth retrying; nothing was concluded
    about the file, so no terminal state is recorded."""


@dataclass(frozen=True)
class ProcessingOutcome:
    run_id: uuid.UUID
    processing_status: EvidenceProcessingStatus | None
    failure_code: ProcessingFailureCode | None
    #: True when this delivery found the work already done and did nothing.
    already_done: bool = False


def abandon_run(
    session: Session,
    *,
    idempotency_key: str,
    code: ProcessingFailureCode,
    summary: str,
) -> ProcessingOutcome | None:
    """Record that a run gave up, so the document does not sit mid-flight forever.

    Called when the retries for a transient failure are exhausted. Without it, the run
    stays RUNNING and the item stays VALIDATING with nothing left to move them: the user
    watches a document that will never resolve, and the client polls it for as long as
    the tab is open. "Failed, and you can try again" is both true and actionable;
    "Validating" forever is neither.

    Returns None if there is no run to abandon — the failure happened before one was
    written, and there is nothing to correct.
    """
    run = _existing_run(session, idempotency_key)
    if run is None:
        return None

    at = utcnow()
    run.fail(code=code, summary=summary, at=at)
    item = session.get(EvidenceItem, run.evidence_item_id)
    if item is not None and item.lifecycle_status is EvidenceLifecycleStatus.ACTIVE:
        item.processing_status = EvidenceProcessingStatus.FAILED.value
        item.updated_at = at
    session.commit()
    return ProcessingOutcome(
        run_id=run.id,
        processing_status=EvidenceProcessingStatus.FAILED,
        failure_code=code,
    )


def _existing_run(session: Session, idempotency_key: str) -> EvidenceProcessingRun | None:
    stmt = select(EvidenceProcessingRun).where(
        EvidenceProcessingRun.idempotency_key == idempotency_key
    )
    return session.execute(stmt).scalar_one_or_none()


def _file_for(
    session: Session, evidence_item_id: uuid.UUID, evidence_file_id: uuid.UUID | None
) -> EvidenceFile | None:
    """The file this delivery is about.

    Named explicitly where the event carried it, so a task acts on the version the event
    described rather than on whatever is newest when it happens to run. Falls back to the
    current file for deliveries written before the id was carried — there is exactly one
    version per item today, so the two agree; the parameter exists so they still agree
    once replacement lands.
    """
    if evidence_file_id is not None:
        return session.execute(
            select(EvidenceFile).where(
                EvidenceFile.id == evidence_file_id,
                EvidenceFile.evidence_item_id == evidence_item_id,
                EvidenceFile.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    return _current_file(session, evidence_item_id)


def _current_file(session: Session, evidence_item_id: uuid.UUID) -> EvidenceFile | None:
    stmt = (
        select(EvidenceFile)
        .where(
            EvidenceFile.evidence_item_id == evidence_item_id,
            EvidenceFile.deleted_at.is_(None),
        )
        .order_by(EvidenceFile.version_number.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def validate_evidence(
    session: Session,
    storage: StorageAdapter,
    *,
    evidence_item_id: uuid.UUID,
    idempotency_key: str,
    trace_id: str | None,
    evidence_file_id: uuid.UUID | None = None,
) -> ProcessingOutcome:
    """Check that the stored bytes are what the upload claimed, and record the run.

    Commits twice, deliberately: once to publish `VALIDATING` so the state is visible
    while the check runs, and once to record the outcome. The tenant survives both
    because ADR-0017 re-applies it on each transaction — this multi-commit shape is
    precisely what that ADR made safe.
    """
    existing = _existing_run(session, idempotency_key)

    if existing is not None and existing.run_status in SETTLED_RUN_STATUSES:
        # A genuine redelivery of work that already reached a verdict. Doing it again
        # would write a second run for one delivery, which is what §16.2 forbids.
        return ProcessingOutcome(
            run_id=existing.id,
            processing_status=PROCESSING_STATUS_FOR_RUN[existing.run_status],
            failure_code=(
                ProcessingFailureCode(existing.failure_code) if existing.failure_code else None
            ),
            already_done=True,
        )

    item = session.get(EvidenceItem, evidence_item_id)
    if item is None or item.lifecycle_status is not EvidenceLifecycleStatus.ACTIVE:
        # §14.5: a deleted evidence item cannot be reprocessed. Nothing is recorded —
        # there is no aggregate left to record it against.
        raise EvidenceNotProcessable(f"evidence item {evidence_item_id} is not active")

    file = _file_for(session, evidence_item_id, evidence_file_id)
    if file is None:
        raise EvidenceNotProcessable(f"evidence item {evidence_item_id} has no file to process")

    if existing is not None:
        # A RUNNING run under this key is **this delivery's own earlier attempt**, not a
        # duplicate: the previous try wrote the run, published VALIDATING, and then hit a
        # transient failure. Treating it as "already done" is what made the retry a
        # silent no-op — the task returned successfully, `request.retries` never
        # advanced, the exhaustion branch never ran, and the document sat in VALIDATING
        # for good. §16.2 allows "a new attempt record"; this is that attempt, counted.
        run = existing
        run.retry_count += 1
    else:
        run = EvidenceProcessingRun.start(
            evidence_item_id=item.id,
            evidence_file_id=file.id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        session.add(run)

    item.processing_status = EvidenceProcessingStatus.VALIDATING.value
    item.updated_at = utcnow()
    try:
        session.commit()
    except IntegrityError:
        # Two deliveries raced past the read above and one lost on the unique key. The
        # loser did nothing, which is the correct outcome for a duplicate.
        session.rollback()
        raced = _existing_run(session, idempotency_key)
        if raced is None:  # pragma: no cover - a genuine integrity bug, not a race
            raise
        return ProcessingOutcome(
            run_id=raced.id,
            processing_status=PROCESSING_STATUS_FOR_RUN[raced.run_status],
            failure_code=None,
            already_done=True,
        )

    try:
        prefix = storage.read_prefix(file.storage_key, length=validation.PREFIX_BYTES)
    except StorageError as exc:
        # Nothing is concluded about the file, so nothing terminal is recorded: the run
        # stays RUNNING and the retry picks it up. Recording FAILED here would tell a
        # user their document is unreadable because our object store had a bad minute.
        raise TransientProcessingError("storage unavailable") from exc

    result = validation.check(prefix, declared=file.media_type)
    at = utcnow()

    if result.matches:
        run.succeed(at=at)
        item.processing_status = EvidenceProcessingStatus.UPLOADED.value
        failure: ProcessingFailureCode | None = None
    else:
        failure = (
            ProcessingFailureCode.EMPTY_FILE
            if not prefix
            else ProcessingFailureCode.CONTENT_DOES_NOT_MATCH_TYPE
        )
        run.fail(
            code=failure,
            # A sentence about the *type*, never about the content. `detected` is a media
            # type this module computed, not anything read out of the document.
            summary=(
                "The file is empty."
                if failure is ProcessingFailureCode.EMPTY_FILE
                else f"This file is not {validation.human_name(file.media_type)}."
            ),
            at=at,
        )
        item.processing_status = EvidenceProcessingStatus.UNSUPPORTED.value

    item.updated_at = at
    session.commit()

    _log.info(
        "evidence.validated",
        evidence_item_id=str(item.id),
        run_id=str(run.id),
        # Media types and a boolean. No filename, no storage key, no content.
        declared_media_type=file.media_type,
        detected_media_type=result.detected,
        matched=result.matches,
        trace_id=trace_id,
    )
    return ProcessingOutcome(
        run_id=run.id,
        processing_status=EvidenceProcessingStatus(item.processing_status),
        failure_code=failure,
    )
