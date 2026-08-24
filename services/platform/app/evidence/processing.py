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
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage import StorageAdapter, StorageError
from app.evidence import extraction, validation
from app.evidence.domain import (
    PIPELINE_VERSION,
    PROCESSING_STATUS_FOR_RUN,
    EvidenceFile,
    EvidenceFileText,
    EvidenceItem,
    EvidenceLifecycleStatus,
    EvidenceProcessingRun,
    EvidenceProcessingStatus,
    ProcessingFailureCode,
    ProcessingRunStatus,
    utcnow,
)

_log = structlog.get_logger()


#: How many times one delivery may attempt the same document before it is declared
#: unreadable. Counts *all* attempts, including redeliveries caused by a worker being
#: killed — which is the case that would otherwise never terminate.
MAX_ATTEMPTS = 3

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
    if run.run_status in SETTLED_RUN_STATUSES:
        # Duplicate delivery is possible by design — `published_at` is committed after
        # the broker accepts — so two deliveries can share one idempotency key. If one
        # exhausts its retries after the other has already succeeded, overwriting would
        # turn a good reading into a FAILED document while `evidence_file_texts` still
        # holds the text. A run that reached a verdict keeps it.
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

    if existing is not None and existing.retry_count >= MAX_ATTEMPTS:
        # The redelivery loop, closed.
        #
        # `task_reject_on_worker_lost` requeues a task whose child was killed — which is
        # exactly what a memory-bomb document produces under a container limit — and the
        # requeue carries the *same* outbox id, so the same idempotency key. The run is
        # still RUNNING, so without this the next delivery bumps `retry_count` and runs
        # the identical parse again, forever, at whatever cost the document chose.
        # Nothing read `retry_count`; now something does.
        at = utcnow()
        existing.fail(
            code=ProcessingFailureCode.RESOURCE_LIMIT,
            summary="This document was too large or too slow to read.",
            at=at,
        )
        item = session.get(EvidenceItem, evidence_item_id)
        if item is not None and item.lifecycle_status is EvidenceLifecycleStatus.ACTIVE:
            item.processing_status = EvidenceProcessingStatus.FAILED.value
            item.updated_at = at
        session.commit()
        _log.warning(
            "evidence.attempts_exhausted",
            evidence_item_id=str(evidence_item_id),
            attempts=existing.retry_count,
        )
        return ProcessingOutcome(
            run_id=existing.id,
            processing_status=EvidenceProcessingStatus.FAILED,
            failure_code=ProcessingFailureCode.RESOURCE_LIMIT,
        )

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
        return _extract(
            session,
            storage,
            item=item,
            file=file,
            run=run,
            detected=result.detected,
            trace_id=trace_id,
        )
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
        "evidence.validation_refused",
        evidence_item_id=str(item.id),
        run_id=str(run.id),
        # Media types and a failure code. No filename, no storage key, no content.
        declared_media_type=file.media_type,
        detected_media_type=result.detected,
        failure_code=failure.value,
        trace_id=trace_id,
    )
    return ProcessingOutcome(
        run_id=run.id,
        processing_status=EvidenceProcessingStatus(item.processing_status),
        failure_code=failure,
    )


def _extract(
    session: Session,
    storage: StorageAdapter,
    *,
    item: EvidenceItem,
    file: EvidenceFile,
    run: EvidenceProcessingRun,
    detected: str | None,
    trace_id: str | None,
) -> ProcessingOutcome:
    """Read the document's native text, and record what was found.

    A third commit, after validation's two. The tenant survives all of them because
    ADR-0017 re-applies it per transaction; publishing `EXTRACTING_TEXT` before the read
    rather than after is what makes the state honest while a slow document is being
    parsed.

    Images are skipped rather than failed. A JPEG is a supported document with no text
    layer to read, which is the same finding as a scanned PDF and gets the same answer.
    """
    item.processing_status = EvidenceProcessingStatus.EXTRACTING_TEXT.value
    item.updated_at = utcnow()
    session.commit()

    if file.media_type != "application/pdf":
        return _finish_without_text(
            session, item=item, run=run, reason="not_a_pdf", trace_id=trace_id
        )

    try:
        content = storage.read(file.storage_key, max_bytes=get_settings().max_upload_bytes)
    except StorageError as exc:
        raise TransientProcessingError("storage unavailable") from exc

    at = utcnow()
    try:
        found = extraction.extract(content)
    except extraction.PasswordProtected:
        return _fail(
            session,
            item=item,
            run=run,
            code=ProcessingFailureCode.PASSWORD_PROTECTED,
            summary="This document is password-protected, so its contents cannot be read.",
            at=at,
            trace_id=trace_id,
        )
    except extraction.UnreadableDocument:
        return _fail(
            session,
            item=item,
            run=run,
            code=ProcessingFailureCode.CORRUPT_FILE,
            summary="This file could not be opened as a PDF.",
            at=at,
            trace_id=trace_id,
        )
    except extraction.ReadTookTooLong:
        return _fail(
            session,
            item=item,
            run=run,
            code=ProcessingFailureCode.RESOURCE_LIMIT,
            summary="This document took too long to read.",
            at=at,
            trace_id=trace_id,
        )

    _record_text(session, file_id=file.id, found=found)

    if found.has_text_layer:
        run.succeed(at=at)
        item.processing_status = EvidenceProcessingStatus.COMPLETED.value
    else:
        # A real, readable document that happens to have no text layer — a scan. Reading
        # it needs OCR or a multimodal model, both M8. `PARTIALLY_COMPLETED` says exactly
        # that: the work was done and there was nothing to find.
        run.partial(at=at)
        item.processing_status = EvidenceProcessingStatus.PARTIALLY_COMPLETED.value
    item.updated_at = at
    session.commit()

    _log.info(
        "evidence.extracted",
        evidence_item_id=str(item.id),
        run_id=str(run.id),
        # Counts and flags. Never the text, never a filename, never a key.
        page_count=found.page_count,
        character_count=found.character_count,
        truncated=found.truncated,
        has_text_layer=found.has_text_layer,
        detected_media_type=detected,
        trace_id=trace_id,
    )
    return ProcessingOutcome(
        run_id=run.id,
        processing_status=EvidenceProcessingStatus(item.processing_status),
        failure_code=None,
    )


def _record_text(session: Session, *, file_id: uuid.UUID, found: extraction.ExtractedText) -> None:
    """Store what was read, replacing any earlier reading of the same bytes.

    One row per file version (Domain §15.1), so a **retry replaces rather than appends**.
    Inserting blindly made a user-initiated retry violate the unique constraint, which is
    the one path this slice exists to support — and the `IntegrityError` would have
    carried the entire document text in its bound parameters had `hide_parameters` not
    been set in slice 1.

    Replacing is also the right answer on its merits: re-reading the same bytes with the
    same pipeline produces the same text, and re-reading them with a *newer* pipeline
    should supersede the old reading rather than sit beside it with no way to tell which
    is current.
    """
    existing = session.execute(
        select(EvidenceFileText).where(EvidenceFileText.evidence_file_id == file_id)
    ).scalar_one_or_none()

    if existing is None:
        session.add(
            EvidenceFileText(
                evidence_file_id=file_id,
                page_count=found.page_count,
                pages_read=found.pages_read,
                character_count=found.character_count,
                content=found.content,
                pipeline_version=PIPELINE_VERSION,
                truncated=found.truncated,
            )
        )
        return

    existing.page_count = found.page_count
    existing.pages_read = found.pages_read
    existing.character_count = found.character_count
    existing.content = found.content
    existing.pipeline_version = PIPELINE_VERSION
    existing.truncated = found.truncated
    existing.extracted_at = utcnow()


def _finish_without_text(
    session: Session,
    *,
    item: EvidenceItem,
    run: EvidenceProcessingRun,
    reason: str,
    trace_id: str | None,
) -> ProcessingOutcome:
    at = utcnow()
    run.partial(at=at)
    item.processing_status = EvidenceProcessingStatus.PARTIALLY_COMPLETED.value
    item.updated_at = at
    session.commit()
    _log.info(
        "evidence.no_text_layer",
        evidence_item_id=str(item.id),
        run_id=str(run.id),
        reason=reason,
        trace_id=trace_id,
    )
    return ProcessingOutcome(
        run_id=run.id,
        processing_status=EvidenceProcessingStatus.PARTIALLY_COMPLETED,
        failure_code=None,
    )


def _fail(
    session: Session,
    *,
    item: EvidenceItem,
    run: EvidenceProcessingRun,
    code: ProcessingFailureCode,
    summary: str,
    at: datetime,
    trace_id: str | None,
) -> ProcessingOutcome:
    run.fail(code=code, summary=summary, at=at)
    item.processing_status = EvidenceProcessingStatus.FAILED.value
    item.updated_at = at
    session.commit()
    _log.info(
        "evidence.extraction_failed",
        evidence_item_id=str(item.id),
        run_id=str(run.id),
        failure_code=code.value,
        trace_id=trace_id,
    )
    return ProcessingOutcome(
        run_id=run.id, processing_status=EvidenceProcessingStatus.FAILED, failure_code=code
    )
