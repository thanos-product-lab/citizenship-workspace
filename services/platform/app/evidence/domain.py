"""EvidenceItem and EvidenceFile aggregates, their enums, and their events.

Domain §14-15. Two shapes worth reading before the code:

**A file version is immutable, and replacing a file appends rather than overwrites**
(§14.5). `EvidenceFile.version_number` sequences within one item, and
`supersedes_file_id` chains them, matching the travel-record convention in `0005`.

**Nothing is persisted until the bytes exist.** The upload is two HTTP calls with a
direct-to-storage PUT between them, but only the second one writes: the storage key
travels through the client inside a server-signed token (`upload_token.py`) rather than
through a reservation row. So an abandoned upload leaves nothing behind, there is no
business state without a domain event to go with it, and `processing_status` needs no
value for "a URL was issued and nothing arrived" — which would have been a change to
§14.4, and so an RFC change (CLAUDE.md §7), for a state no user can observe.

Every column below is therefore populated at creation: an `EvidenceItem` that exists is
a document the case really holds, and an `EvidenceFile` that exists has bytes behind it.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.errors import IllegalTransition
from app.shared.messaging import DomainEvent


class EvidenceCategory(StrEnum):
    """Domain §14.2, verbatim.

    §14.2: `OTHER` and `UNKNOWN` "can be stored but cannot create trusted domain facts
    without a supported review path". Nothing creates a fact from evidence until M8, so
    that constraint has no enforcement point yet — it arrives with `FactEvidenceLink`.
    """

    IMMIGRATION_STATUS = "IMMIGRATION_STATUS"
    ENGLISH_LANGUAGE = "ENGLISH_LANGUAGE"
    LIFE_IN_THE_UK = "LIFE_IN_THE_UK"
    TRAVEL_SUPPORT = "TRAVEL_SUPPORT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class EvidenceLifecycleStatus(StrEnum):
    """Domain §14.3, verbatim."""

    ACTIVE = "ACTIVE"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"


class EvidenceProcessingStatus(StrEnum):
    """Domain §14.4, verbatim — and the *only* vocabulary the API may project.

    These are domain states. Raw Celery states (`PENDING`, `STARTED`, `RETRY`, …) are
    never shown to a user (Technical Architecture RFC §18, MVP §8.9), and
    `tests/evidence/test_processing_states.py` asserts none of them can reach a
    response.

    Reachability in M7: `UPLOADED` here in slice 1; `VALIDATING` in slice 2;
    `EXTRACTING_TEXT`, `ANALYSING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`,
    `UNSUPPORTED` in slice 3. `AWAITING_CONFIRMATION` has no producer until claims
    exist in M8, and ships unreachable rather than faked — the UI must not offer it as
    a stage a document might enter.
    """

    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    EXTRACTING_TEXT = "EXTRACTING_TEXT"
    ANALYSING = "ANALYSING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


# States a document does not leave on its own. Slice 3's retry policy and the frontend's
# polling both read this, so "when do we stop asking" is defined once.
TERMINAL_PROCESSING_STATUSES = frozenset(
    {
        EvidenceProcessingStatus.COMPLETED,
        EvidenceProcessingStatus.PARTIALLY_COMPLETED,
        EvidenceProcessingStatus.FAILED,
        EvidenceProcessingStatus.UNSUPPORTED,
        EvidenceProcessingStatus.AWAITING_CONFIRMATION,
    }
)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    category: Mapped[str] = mapped_column(String(30))
    # User-facing label. Untrusted input: rendered, never used to build a storage path.
    display_name: Mapped[str] = mapped_column(String(255))
    _lifecycle_status: Mapped[str] = mapped_column("lifecycle_status", String(20))
    processing_status: Mapped[str] = mapped_column(String(30))
    # App-maintained pointer, no circular FK (the 0003/0005 convention).
    current_file_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012

    @classmethod
    def uploaded(
        cls,
        *,
        case_id: uuid.UUID,
        category: EvidenceCategory,
        display_name: str,
        created_by: str,
    ) -> "EvidenceItem":
        """A new item, at the moment its bytes are known to exist.

        `UPLOADED` is the honest first state: the object is in the store and nothing has
        looked at it yet. Slice 2 moves it on to `VALIDATING`.
        """
        return cls(
            id=uuid.uuid4(),
            case_id=case_id,
            category=category.value,
            display_name=display_name,
            _lifecycle_status=EvidenceLifecycleStatus.ACTIVE.value,
            processing_status=EvidenceProcessingStatus.UPLOADED.value,
            created_by=created_by,
            revision=1,
        )

    @property
    def lifecycle_status(self) -> EvidenceLifecycleStatus:
        return EvidenceLifecycleStatus(self._lifecycle_status)

    @property
    def is_active(self) -> bool:
        return self.lifecycle_status is EvidenceLifecycleStatus.ACTIVE

    def point_at_file(self, *, file_id: uuid.UUID, at: datetime) -> None:
        """Make a file version the item's current one.

        Refuses on a non-ACTIVE item: §14.5, "a deleted evidence item cannot be
        reprocessed", and adding a file version to a deleted item is the same move.
        """
        if not self.is_active:
            raise IllegalTransition(f"evidence item is {self._lifecycle_status}")
        self.current_file_id = file_id
        self.updated_at = at


class EvidenceFile(Base):
    """One immutable file version of an evidence item (Domain §15)."""

    __tablename__ = "evidence_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    # Server-generated and recorded here *before* any URL is signed for it. §15:
    # "storage_key is never treated as authorisation" — every read re-checks ownership.
    storage_key: Mapped[str] = mapped_column(String(500))
    # Untrusted. Metadata only: never part of the storage path (threat model §12), and
    # encoded per RFC 6266 before it reaches a Content-Disposition header.
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    # Read from the store, never from the request: a client has already said what it
    # intended to upload, and this is what it actually did.
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(128))
    encryption_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # When the object was confirmed present in the store.
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_file_id: Mapped[uuid.UUID | None] = mapped_column()

    @classmethod
    def landed(
        cls,
        *,
        evidence_item_id: uuid.UUID,
        version_number: int,
        storage_key: str,
        original_filename: str | None,
        media_type: str,
        size_bytes: int,
        checksum: str,
        at: datetime,
        supersedes_file_id: uuid.UUID | None = None,
    ) -> "EvidenceFile":
        """A file version whose bytes are confirmed present."""
        return cls(
            id=uuid.uuid4(),
            evidence_item_id=evidence_item_id,
            version_number=version_number,
            storage_key=storage_key,
            original_filename=original_filename,
            media_type=media_type,
            size_bytes=size_bytes,
            checksum=checksum,
            uploaded_at=at,
            supersedes_file_id=supersedes_file_id,
        )

    @property
    def is_available(self) -> bool:
        return self.deleted_at is None


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- events ------------------------------------------------------------------------
#
# Payload rule (Domain §38.1): identifiers, enums, version numbers and reason codes
# only. No filename, no storage key, no document content — §38.1 and threat model §6.4.


@dataclass(frozen=True)
class EvidenceUploaded(DomainEvent):
    aggregate_type: ClassVar[str] = "EvidenceItem"
    event_type: ClassVar[str] = "EvidenceUploaded"

    case_id: uuid.UUID
    evidence_file_id: uuid.UUID
    category: str
    media_type: str
    size_bytes: int

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "evidence_item_id": str(self.aggregate_id),
            "evidence_file_id": str(self.evidence_file_id),
            "category": self.category,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
        }


# --- processing runs ---------------------------------------------------------------


class ProcessingRunStatus(StrEnum):
    """Domain §16.1, verbatim. **Internal**: this is the worker's vocabulary, and it is
    never projected to a user. `PROCESSING_STATUS_FOR_RUN` below maps it onto the §14.4
    states the API is allowed to speak."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingFailureCode(StrEnum):
    """Why a run stopped, as a stable code.

    Codes, never prose, for the same reason `AssessmentResult` uses summary codes: a
    message is written once and read forever, and an exception string carries whatever
    the driver felt like including — in slice 1 that turned out to be the storage key and
    the original filename (ADR-0019).

    Split by whether a retry could ever help, which is what `TRANSIENT_FAILURE_CODES`
    below encodes:

    - **Terminal.** The file is what it is; running again produces the same answer.
    - **Transient.** The store or the network was unavailable; the same file may well
      succeed in ten seconds.
    """

    # Terminal — Technical Architecture RFC §18, "do not automatically retry".
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    CONTENT_DOES_NOT_MATCH_TYPE = "CONTENT_DOES_NOT_MATCH_TYPE"
    CORRUPT_FILE = "CORRUPT_FILE"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_FILE = "EMPTY_FILE"
    # Transient — retried with backoff.
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    TIMED_OUT = "TIMED_OUT"


TRANSIENT_FAILURE_CODES = frozenset(
    {ProcessingFailureCode.STORAGE_UNAVAILABLE, ProcessingFailureCode.TIMED_OUT}
)

#: How a run's internal status becomes the state a user is shown (§14.4).
#:
#: Total over `ProcessingRunStatus` on purpose, and asserted to be in
#: `tests/evidence/test_processing_states.py`: a status with no mapping would otherwise
#: fall through to whatever the item already said, which is the quiet failure mode —
#: a document that finished and still reads as though nothing happened.
#:
#: `SUCCEEDED` maps back to `UPLOADED` in this slice because validation is all that
#: runs: the file is stored, it has been checked, and nothing has read its contents.
#: That is exactly what `UPLOADED` means and exactly what the library says. Slice 3
#: carries the same run on into extraction, where `SUCCEEDED` becomes `COMPLETED`.
PROCESSING_STATUS_FOR_RUN: dict[ProcessingRunStatus, EvidenceProcessingStatus | None] = {
    ProcessingRunStatus.QUEUED: EvidenceProcessingStatus.UPLOADED,
    ProcessingRunStatus.RUNNING: EvidenceProcessingStatus.VALIDATING,
    ProcessingRunStatus.SUCCEEDED: EvidenceProcessingStatus.UPLOADED,
    ProcessingRunStatus.PARTIAL: EvidenceProcessingStatus.PARTIALLY_COMPLETED,
    ProcessingRunStatus.FAILED: EvidenceProcessingStatus.FAILED,
    # A cancelled run leaves the item's state alone: the case or the document is being
    # deleted, and "Failed" would tell the user their document could not be processed
    # when what happened is that they deleted it.
    ProcessingRunStatus.CANCELLED: None,
}

#: Bumped when the deterministic pipeline changes in a way that would produce a
#: different result for the same bytes. Not a `RuleVersion` and carries no eligibility
#: meaning — it versions a mechanism, not a conclusion.
PIPELINE_VERSION = "m7.validate.1"


class EvidenceProcessingRun(Base):
    """One execution of the processing pipeline against one exact file version (§16)."""

    __tablename__ = "evidence_processing_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    # §16.2: "a run cannot process a file version different from the one recorded."
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.id"))
    status: Mapped[str] = mapped_column(String(20))
    pipeline_version: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(40))
    # A short, safe sentence. Never an exception string and never document content
    # (§16.2: "failure summaries must not contain raw document content").
    failure_summary: Mapped[str | None] = mapped_column(String(200))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    #: **The outbox row's own id.** Making the delivery identity the idempotency identity
    #: gets both cases right with no extra state: a duplicate delivery reuses the row and
    #: so collides here, while a user-initiated retry writes a *new* outbox row and so
    #: gets a genuinely new run. Keying on `file_id:pipeline_version` instead cannot tell
    #: those apart.
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)

    @classmethod
    def start(
        cls,
        *,
        evidence_item_id: uuid.UUID,
        evidence_file_id: uuid.UUID,
        idempotency_key: str,
        trace_id: str | None,
    ) -> "EvidenceProcessingRun":
        return cls(
            id=uuid.uuid4(),
            evidence_item_id=evidence_item_id,
            evidence_file_id=evidence_file_id,
            status=ProcessingRunStatus.RUNNING.value,
            pipeline_version=PIPELINE_VERSION,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

    @property
    def run_status(self) -> ProcessingRunStatus:
        return ProcessingRunStatus(self.status)

    def succeed(self, *, at: datetime) -> None:
        self.status = ProcessingRunStatus.SUCCEEDED.value
        self.completed_at = at

    def fail(self, *, code: ProcessingFailureCode, summary: str, at: datetime) -> None:
        self.status = ProcessingRunStatus.FAILED.value
        self.failure_code = code.value
        self.failure_summary = summary[:200]
        self.completed_at = at

    def cancel(self, *, at: datetime) -> None:
        self.status = ProcessingRunStatus.CANCELLED.value
        self.completed_at = at
