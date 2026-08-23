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
