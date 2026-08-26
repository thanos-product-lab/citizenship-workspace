"""Evidence commands. Domain logic lives here, not in the route handlers.

Slice 1 is the upload path, and it is two commands rather than one because of where the
storage key has to come from.

    POST .../evidence/uploads        reserve  -> item + file row + presigned PUT URL
    (client PUTs the bytes straight to private storage)
    POST .../evidence/{id}/complete  confirm  -> HEAD the object, record what it says

The alternative — create the record *after* the upload, as the Architecture RFC §18
step list reads — would need the client to hand back the key it uploaded to. A
client-supplied key is a client-supplied storage path, and threat model §12 requires
server-generated ones. So the key is minted and recorded first, and the presigned URL is
signed for that key alone.

**Validation is split, deliberately.** Media type and declared size are refused at
presign, before a byte is written — MVP §8.9's "rejected before processing". Actual size
comes from the store at completion, because what a client declares is not what it
uploads. Magic-byte verification needs the content itself and belongs to the worker's
`VALIDATING` state in slice 2; until then a file whose bytes contradict its declared
type reaches `UPLOADED` and no further. That is the honest reading of "before
processing", not a gap.

Nothing here trusts a storage key, or a token, as authorisation (Domain §52). Every path
re-reads the item through `get_active_for_case`, the case arrives from
`require_case_access`, and the token carries integrity only - it proves the server minted
the key, never that the caller may use it.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.schemas import CurrentUser
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.core.config import get_settings
from app.core.storage import StorageAdapter, build_key
from app.evidence import upload_token
from app.evidence.domain import (
    USER_RETRYABLE_FAILURE_CODES,
    EvidenceCategory,
    EvidenceFile,
    EvidenceItem,
    EvidenceProcessingRequested,
    EvidenceProcessingStatus,
    EvidenceUploaded,
    ProcessingFailureCode,
    utcnow,
)
from app.evidence.repository import EvidenceRepository
from app.issues import service as issues_service
from app.shared.errors import (
    CaseNotActive,
    EvidenceNotFound,
    EvidenceNotRetryable,
    EvidenceRetryTooSoon,
    EvidenceTooLarge,
    EvidenceUploadIncomplete,
    UnsupportedEvidenceType,
)
from app.shared.unit_of_work import UnitOfWork

# The document types this product can actually read. PDF is the real target; the image
# types exist because a phone photo of a letter is what people have. Anything else is
# refused at presign rather than accepted and then failed, so the user finds out before
# waiting for an upload (MVP §8.9).
SUPPORTED_MEDIA_TYPES: tuple[str, ...] = (
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
)


@dataclass(frozen=True)
class UploadGrant:
    """What the client needs to perform the upload, and nothing more."""

    upload_url: str
    upload_fields: dict[str, str]
    upload_token: str
    media_type: str
    expires_in_seconds: int


def _require_active_case(case: ApplicationCase) -> None:
    """Evidence exists to support an assessment, and a case that cannot be assessed
    cannot hold any. Mirrors `residence._require_active_writable_case`; a non-active
    case is a 409 with a code, never a 404 — it is real and owned, just not ready."""
    if case.lifecycle_status is not LifecycleStatus.ACTIVE:
        raise CaseNotActive(case.lifecycle_status.value)


def start_upload(
    storage: StorageAdapter,
    *,
    case: ApplicationCase,
    media_type: str,
    declared_size_bytes: int,
) -> UploadGrant:
    """Mint a storage key and sign a URL and a token for it. Writes nothing.

    Refusing the media type and the declared size here is MVP §8.9's "unsupported file
    types are rejected before processing" in its strongest form: the user finds out
    before uploading, and no object is ever written for a type this product cannot read.
    The type is also bound into the presigned URL's signature, so it is the only type
    the store will accept at that URL.
    """
    _require_active_case(case)

    settings = get_settings()
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise UnsupportedEvidenceType(media_type, SUPPORTED_MEDIA_TYPES)
    if declared_size_bytes > settings.max_upload_bytes:
        raise EvidenceTooLarge(declared_size_bytes, settings.max_upload_bytes)

    ttl = settings.storage_presign_ttl_seconds
    key = build_key(case_id=case.id)
    signed = storage.presigned_upload(
        key,
        media_type=media_type,
        ttl_seconds=ttl,
        # The ceiling goes into the signed policy, so the store refuses an oversized
        # body outright. `declared_size_bytes` above only buys the user an early "no";
        # this is what makes the limit a control.
        max_bytes=settings.max_upload_bytes,
    )
    return UploadGrant(
        upload_url=signed.url,
        upload_fields=signed.fields,
        upload_token=upload_token.issue(
            case_id=case.id, storage_key=key, media_type=media_type, ttl_seconds=ttl
        ),
        media_type=media_type,
        expires_in_seconds=ttl,
    )


def record_upload(
    session: Session,
    storage: StorageAdapter,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    token: str,
    category: EvidenceCategory,
    display_name: str,
    original_filename: str | None,
) -> tuple[EvidenceItem, EvidenceFile]:
    """Confirm the bytes are really there, then record the document.

    Size and checksum come from the store, never from the request: the client has
    already said what it intended to upload, and this is where we find out what it did.

    State, event, audit entry and outbox row commit together through `UnitOfWork`, or
    not at all.
    """
    _require_active_case(case)

    grant = upload_token.verify(token, case_id=case.id)

    # Recording is idempotent on the storage key, and that is a correctness property
    # rather than a nicety. This is the retry-prone call in the sequence: the bytes are
    # already in the store, so a client that loses this response will send it again.
    # Without this the second attempt violates `uq_evidence_files_storage_key`, and the
    # resulting IntegrityError carries SQLAlchemy's bound parameters — the storage key,
    # the original filename and the checksum — into a 500 and out into the logs, which
    # is exactly what threat model §6.4 forbids.
    existing = EvidenceRepository.get_by_storage_key(
        session, case_id=case.id, storage_key=grant.storage_key
    )
    if existing is not None:
        return existing

    stored = storage.head(grant.storage_key)
    if stored is None:
        raise EvidenceUploadIncomplete()

    settings = get_settings()
    if stored.size_bytes > settings.max_upload_bytes:
        # The declared size passed and the real one did not. The object is left for the
        # purge path rather than deleted here: nothing outside the deletion path ever
        # removes stored content, which is what keeps "processing failure never deletes
        # the uploaded evidence" a property of the code's shape rather than a promise.
        raise EvidenceTooLarge(stored.size_bytes, settings.max_upload_bytes)

    at = utcnow()
    item = EvidenceItem.uploaded(
        case_id=case.id,
        category=category,
        display_name=display_name,
        created_by=user.user_id,
    )
    EvidenceRepository.add_item(session, item)
    # Flush before the child: SQLAlchemy orders a flush from `relationship()`
    # dependencies, and these aggregates are joined by an app-maintained pointer rather
    # than a relationship (the 0003/0005 convention). Without this the file row inserts
    # first and `evidence_files`' RLS policy - which predicates through its parent -
    # correctly refuses a row whose parent does not exist yet.
    session.flush()

    file = EvidenceFile.landed(
        evidence_item_id=item.id,
        version_number=1,
        storage_key=grant.storage_key,
        original_filename=original_filename,
        media_type=grant.media_type,
        size_bytes=stored.size_bytes,
        checksum=stored.etag,
        at=at,
    )
    EvidenceRepository.add_file(session, file)
    session.flush()
    item.point_at_file(file_id=file.id, at=at)

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        EvidenceUploaded(
            aggregate_id=item.id,
            case_id=case.id,
            evidence_file_id=file.id,
            category=item.category,
            media_type=file.media_type,
            size_bytes=file.size_bytes,
        ),
        case_id=case.id,
        action="EVIDENCE_UPLOADED",
        target_type="EvidenceItem",
        target_id=item.id,
        # Safe metadata only (Domain §38.1): no filename, no key, no content.
        safe_metadata={"category": item.category, "media_type": file.media_type},
    )
    # Uploading changes the *desired issue set* even though it stales nothing.
    #
    # `MISSING_EVIDENCE` is suppressed until the case holds a document (see
    # `issues.derivation._missing_evidence_issues`). Without this call the gate flipped
    # true with nothing to notice, so the coverage items first appeared at the next
    # invalidating write — which is the first *attach*. That is precisely the behaviour
    # the gate was written to avoid: the user attaches one booking and is handed an issue
    # for every trip they have not got to yet, which reads as being punished for progress.
    #
    # Not `invalidate_for_input_change`: no conclusion has gone out of date. A document
    # arriving in the library changes no input any rule reads — only whether the queue is
    # ready to name the gaps. Staling results here would be over-firing.
    issues_service.reconcile(session, uow, case_id=case.id)
    uow.commit()
    return item, file


def list_evidence(
    session: Session, *, case: ApplicationCase
) -> list[tuple[EvidenceItem, EvidenceFile]]:
    return EvidenceRepository.list_uploaded_for_case(session, case_id=case.id)


def get_evidence(
    session: Session, *, case: ApplicationCase, evidence_item_id: uuid.UUID
) -> tuple[EvidenceItem, EvidenceFile]:
    item = EvidenceRepository.get_active_for_case(
        session, case_id=case.id, evidence_item_id=evidence_item_id
    )
    if item is None:
        raise EvidenceNotFound()
    file = EvidenceRepository.get_current_file(session, evidence_item_id=item.id)
    if file is None or not file.is_available:
        raise EvidenceNotFound()
    return item, file


def content_url(
    session: Session,
    storage: StorageAdapter,
    *,
    case: ApplicationCase,
    evidence_item_id: uuid.UUID,
) -> tuple[str, int]:
    """A short-lived, case-authorised URL for the file's content.

    The ownership check happens here, before the URL exists — the URL is a consequence
    of authorisation, never a substitute for it (Domain §52). It cannot be revoked once
    issued, so its TTL is the whole of its life; see ADR-0018.
    """
    item, file = get_evidence(session, case=case, evidence_item_id=evidence_item_id)
    settings = get_settings()
    return (
        storage.presigned_get_url(
            file.storage_key,
            ttl_seconds=settings.storage_presign_ttl_seconds,
            download_filename=file.original_filename or item.display_name,
        ),
        settings.storage_presign_ttl_seconds,
    )


#: States a user may ask us to try again from.
#:
#: Deliberately not `UNSUPPORTED`: that verdict is about the *file*, and running the same
#: bytes through the same check reaches the same answer. A button that cannot work is
#: worse than no button — the honest action is to upload a different file.
#:
#: `FAILED` covers the resource-limit case too, which is why a document the worker could
#: not finish reading is retryable by a *person* while not being retried automatically:
#: three more attempts at a document that already exhausted a bound is three more chances
#: to take a worker down, but a user who knows the system was busy should be able to ask
#: again.
#: How long after an attempt starts before another may be asked for.
RETRY_COOLDOWN_SECONDS = 30.0

RETRYABLE_STATUSES = frozenset(
    {
        EvidenceProcessingStatus.FAILED,
        EvidenceProcessingStatus.PARTIALLY_COMPLETED,
    }
)


def may_retry(status: EvidenceProcessingStatus, failure_code: str | None) -> bool:
    """Whether asking again could reach a different answer.

    The status alone is not enough, which is what the browser check found: `FAILED`
    covers both a worker stopped by its own resource bound — worth another go, the box
    may simply have been busy — and a password-protected document, which is
    password-protected every time. Both were offered "Read it again"; pressing it on the
    second spent a worker slot to reach the identical failure.

    `PARTIALLY_COMPLETED` stays retryable regardless. Re-reading a scan does yield a scan,
    so the answer is usually the same, but that is a *reading* the user may reasonably
    want repeated after replacing the file's contents is not an option — and the cooldown
    below is what stops it becoming a loop.

    One function, used by the guard and by the projection that draws the button, so the
    screen cannot offer what the command will refuse.
    """
    if status is EvidenceProcessingStatus.PARTIALLY_COMPLETED:
        return True
    if status is not EvidenceProcessingStatus.FAILED:
        return False
    # No code recorded: the run failed in a way nothing classified, so nothing can say
    # the file is at fault. Offer the retry rather than closing the only door.
    if failure_code is None:
        return True
    try:
        return ProcessingFailureCode(failure_code) in USER_RETRYABLE_FAILURE_CODES
    except ValueError:
        # A code this build does not know. Same reasoning as above.
        return True


def request_reprocessing(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    evidence_item_id: uuid.UUID,
) -> tuple[EvidenceItem, EvidenceFile]:
    """Ask for a document to be processed again.

    Writes a **new outbox row**, which is the whole mechanism: the idempotency key is the
    outbox row's id, so a new row is a new key, and the run is not short-circuited as a
    duplicate. Nothing about the file changes and nothing is deleted — a retry is a new
    attempt at reading the same bytes, not a re-upload.
    """
    _require_active_case(case)

    item, file = get_evidence(session, case=case, evidence_item_id=evidence_item_id)
    current = EvidenceProcessingStatus(item.processing_status)
    latest_run = EvidenceRepository.latest_run(session, evidence_item_id=item.id)
    if not may_retry(current, latest_run.failure_code if latest_run else None):
        raise EvidenceNotRetryable(current.value)

    # A cooldown, because two of the retryable states are deterministic. Re-reading a
    # scan yields a scan, so `PARTIALLY_COMPLETED` returns to `PARTIALLY_COMPLETED` and
    # the button is available again immediately — an unbounded loop by construction, each
    # turn costing a full parse on a shared queue. There is no rate limiting anywhere in
    # this application yet, so the bound lives here, on the one command that is cheap to
    # ask for and expensive to serve.
    if latest_run is not None:
        since = (utcnow() - latest_run.started_at).total_seconds()
        if since < RETRY_COOLDOWN_SECONDS:
            raise EvidenceRetryTooSoon(int(RETRY_COOLDOWN_SECONDS - since))

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        EvidenceProcessingRequested(
            aggregate_id=item.id,
            case_id=case.id,
            evidence_file_id=file.id,
            previous_status=current.value,
        ),
        case_id=case.id,
        action="EVIDENCE_REPROCESSING_REQUESTED",
        target_type="EvidenceItem",
        target_id=item.id,
        safe_metadata={"previous_status": current.value},
    )
    # Back to a state that says something is happening, so the client resumes polling
    # rather than showing a stale terminal verdict until the next reload.
    item.processing_status = EvidenceProcessingStatus.VALIDATING.value
    item.updated_at = utcnow()
    uow.commit()
    return item, file
