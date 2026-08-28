"""Destroying a document's content (Domain §51.1, steps 3 and 7).

**The only code path in the product that destroys user content.** Nothing on the upload or
processing path can reach it: it runs solely from `EvidenceDeleted`, which only
`service.delete_evidence` emits.

Three properties it has to hold, and the reasoning behind each:

**It refuses anything that is not `DELETION_PENDING`.** The command that blocks access is
the only thing that puts an item there, so this cannot destroy the content of a document a
user can still reach. If the state is wrong the task returns rather than raising — a purge
for an item nobody asked to delete is a bug to fix, not work to retry forever.

**Bytes first, record second.** The storage key is what addresses the object, so clearing
it before the delete would strand the content with nothing pointing at it. If the object
delete succeeds and the commit then fails, redelivery re-deletes (a no-op against S3) and
completes the record. The reverse order can lose the object permanently.

**It emits no domain event.** `EvidenceDeleted` already recorded what happened; the purge
carries it out. A second event would assert a new fact where there is only a consequence,
and it would have to be written *after* the tombstone — the one place a name or a key must
never be recorded. This follows `processing.py`, which likewise commits directly: the
worker completes work an event already announced rather than announcing more.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import StorageAdapter, StorageError
from app.evidence.domain import (
    EvidenceFile,
    EvidenceFileText,
    EvidenceItem,
    EvidenceLifecycleStatus,
    utcnow,
)
from app.issues import service as issues_service

_log = structlog.get_logger()


@dataclass(frozen=True)
class PurgeOutcome:
    evidence_item_id: uuid.UUID
    #: False when there was nothing left to do — an already-purged item under redelivery.
    purged: bool
    reason: str


def purge_evidence(
    session: Session,
    storage: StorageAdapter,
    *,
    evidence_item_id: uuid.UUID,
    trace_id: str | None = None,
) -> PurgeOutcome:
    """Delete the object, then leave a tombstone.

    Raises `StorageError` when the store cannot be reached, so the task retries and the
    item stays `DELETION_PENDING`. That is the honest intermediate state: access is already
    blocked and nothing depends on the document, so a delayed purge is incomplete rather
    than wrong.
    """
    item = session.get(EvidenceItem, evidence_item_id)
    if item is None:
        # The row is a tombstone, not a deletion, so this should not happen — but a purge
        # for something absent has nothing to destroy and nothing to record.
        return PurgeOutcome(evidence_item_id, purged=False, reason="absent")

    if item.lifecycle_status is EvidenceLifecycleStatus.DELETED:
        # Redelivery. The relay is at-least-once and this is the expected second pass.
        return PurgeOutcome(evidence_item_id, purged=False, reason="already_purged")

    if item.lifecycle_status is not EvidenceLifecycleStatus.DELETION_PENDING:
        # ACTIVE. Nobody asked for this document to be deleted, so destroying its content
        # would be the worst kind of bug this module could have. Returning rather than
        # raising: retrying cannot make an unrequested deletion correct.
        _log.error(
            "evidence.purge_refused",
            evidence_item_id=str(evidence_item_id),
            lifecycle_status=item.lifecycle_status.value,
            trace_id=trace_id,
        )
        return PurgeOutcome(evidence_item_id, purged=False, reason="not_pending")

    files = list(
        session.execute(
            select(EvidenceFile).where(EvidenceFile.evidence_item_id == evidence_item_id)
        ).scalars()
    )

    at = utcnow()
    for file in files:
        # Every version, not just the current one. A replaced document's earlier bytes are
        # as much the user's content as the latest, and §51.1 says delete the content — a
        # purge that left superseded versions in the bucket would be deleting the pointer
        # rather than the document.
        storage.delete(file.storage_key)

    _tombstone(session, item, files, at=at)
    item.mark_deleted(at=at)
    session.commit()

    _log.info(
        "evidence.purged",
        evidence_item_id=str(evidence_item_id),
        file_versions=len(files),
        trace_id=trace_id,
    )
    return PurgeOutcome(evidence_item_id, purged=True, reason="purged")


def _tombstone(
    session: Session, item: EvidenceItem, files: list[EvidenceFile], *, at: datetime
) -> None:
    """Keep the minimal non-sensitive record §51.1 step 7 asks for, and nothing else.

    Kept: ids, `case_id`, `category`, `media_type`, `size_bytes`, the timestamps, and the
    **storage key**. The key is server-generated randomness plus a case id the row already
    carries, so it identifies nothing new; after the delete above it addresses nothing; and
    keeping it leaves an operator able to re-check the object if a purge is ever suspected
    of having failed. (`uq_evidence_files_storage_key` is a plain unique constraint, so
    blanking it would also collide on the second deletion — but that is the lesser reason.)

    Cleared:

    - `display_name` — the user's own words for their document.
    - `original_filename` — very often a real name, and untrusted input besides.
    - `checksum` — a *content fingerprint*. Retaining it would let anyone with database
      access confirm whether a specific known document had ever been uploaded here, which
      is precisely the question a deletion is meant to stop answering.
    - the extracted text row, deleted outright. There is no minimal non-sensitive version
      of a document's text; the text *is* the document.
    - the same name where `issues` copied it. `DUPLICATE_EVIDENCE` denormalises
      `display_name` and `other_name` into `message_parameters`, and resolving an issue
      leaves those untouched — so clearing the column alone left the user's words for a
      destroyed document in two resolved rows. Cleared through a seam in `issues` rather
      than by reaching into its table from here.
    """
    # Before the name is blanked below: the twin's row holds it as a string, so this is
    # the last point at which it can be matched.
    issues_service.forget_evidence_names(
        session,
        case_id=item.case_id,
        evidence_item_id=item.id,
        display_name=item.display_name,
    )

    item.display_name = ""
    item.updated_at = at
    for file in files:
        file.original_filename = None
        file.checksum = ""
        file.deleted_at = at
    for text in session.execute(
        select(EvidenceFileText).where(
            EvidenceFileText.evidence_file_id.in_([file.id for file in files])
        )
    ).scalars():
        session.delete(text)


__all__ = ["PurgeOutcome", "StorageError", "purge_evidence"]
