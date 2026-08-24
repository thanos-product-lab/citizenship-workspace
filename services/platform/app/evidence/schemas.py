"""Evidence wire types.

Two rules this module exists to hold:

- **`processing_status` is typed to the §14.4 enum**, not to `str`. A raw Celery state
  cannot be serialised through a field whose type does not contain it, which is the
  structural half of "domain processing states shown - never raw Celery states"
  (MVP §8.9). The grep test in `tests/evidence/test_processing_states.py` is the other
  half, for the paths that do not go through a schema.
- **No document content crosses this boundary in M7.** Not the extracted text, not an
  excerpt, not a page of it. Slice 3 adds `page_count` and `character_count` and a short
  excerpt; full text waits for M8's review surface. Tier-3 content (threat model §3)
  stays out of API responses, out of the Next.js server's memory, and out of any error
  reporter's breadcrumbs for as long as there is no screen that needs it.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.evidence.domain import (
    EvidenceCategory,
    EvidenceFile,
    EvidenceFileText,
    EvidenceItem,
    EvidenceLifecycleStatus,
    EvidenceProcessingRun,
    EvidenceProcessingStatus,
)
from app.evidence.service import RETRYABLE_STATUSES, SUPPORTED_MEDIA_TYPES, UploadGrant


class StartUploadRequest(BaseModel):
    """What the client declares before uploading. Both fields are untrusted.

    `declared_size_bytes` buys the user an early refusal on an obviously oversized file
    rather than a failure after the upload; the store's own count is checked again when
    the document is recorded, and that is the number that counts.
    """

    media_type: str = Field(max_length=120)
    declared_size_bytes: int = Field(ge=0)


class UploadGrantResponse(BaseModel):
    """The presigned PUT, and the signed token that carries the storage key back.

    The token is opaque to the client and is not a capability: presenting it proves the
    server minted the key, never that the caller may use it. Ownership is re-checked on
    the recording call like every other route.
    """

    upload_url: str
    # The signed policy fields that must accompany the file in the multipart POST. They
    # carry the key, the content type and the size ceiling, and the signature covers all
    # of them — so a client can send this form or nothing, but cannot amend it.
    upload_fields: dict[str, str]
    upload_token: str
    expires_in_seconds: int
    # Echoed so the client sends exactly the type that was signed; a mismatch is
    # refused by the store, not by us.
    media_type: str

    @classmethod
    def from_domain(cls, grant: UploadGrant) -> "UploadGrantResponse":
        return cls(
            upload_url=grant.upload_url,
            upload_fields=grant.upload_fields,
            upload_token=grant.upload_token,
            expires_in_seconds=grant.expires_in_seconds,
            media_type=grant.media_type,
        )


class RecordUploadRequest(BaseModel):
    """The document's user-facing metadata, plus the token from the grant."""

    upload_token: str
    category: EvidenceCategory
    display_name: str = Field(min_length=1, max_length=255)
    # Metadata only. Never part of a storage path (threat model §12), and encoded per
    # RFC 6266 before it reaches a Content-Disposition header.
    original_filename: str | None = Field(default=None, max_length=255)


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    category: EvidenceCategory
    display_name: str
    lifecycle_status: EvidenceLifecycleStatus
    # Optional because an item can exist before its bytes do — such an item is never
    # projected, so in practice this is always set here. Typed to the domain enum so a
    # queue state cannot be serialised in its place.
    processing_status: EvidenceProcessingStatus
    #: Why processing stopped, when it did. A document reading "Unsupported" with no
    #: reason is a dead end: the user cannot tell whether to re-export the file, try a
    #: different one, or give up. The code is for the client, the sentence for the person
    #: — and neither ever contains document content (§16.2).
    failure_code: str | None = None
    failure_reason: str | None = None
    #: What extraction found, as counts — **never the text, and not even an excerpt**.
    #:
    #: An excerpt was here and was removed: nothing consumed it, and the counts already
    #: prove extraction worked. Shipping 280 characters of a document in every library
    #: response, for a screen whose job is to say "this worked", is the surface §7.4
    #: exists to avoid — sitting in a response, in the Next.js server's memory, and in
    #: any error reporter's breadcrumbs, for no reader.
    #: Domain §15.1 and §7.4 of the M7 plan: full document text stays server-side until
    #: M8 has a review surface designed for it, so Tier-3 content does not sit in an API
    #: response, in the Next.js server's memory, or in an error reporter's breadcrumbs
    #: for the sake of a screen that only has to say "this worked".
    page_count: int | None = None
    pages_read: int | None = None
    character_count: int | None = None
    #: A cap stopped the read. Shown, because a user looking at a 400-page document
    #: should know only the first 40 were read.
    text_truncated: bool = False
    #: Whether a retry would do anything. Computed here rather than in the client so the
    #: rule lives in one place — the client must not decide `UNSUPPORTED` is retryable.
    can_retry: bool = False
    media_type: str
    size_bytes: int
    original_filename: str | None
    uploaded_at: datetime
    created_at: datetime
    revision: int

    @classmethod
    def from_domain(
        cls,
        item: EvidenceItem,
        file: EvidenceFile,
        run: EvidenceProcessingRun | None = None,
        text: EvidenceFileText | None = None,
    ) -> "EvidenceResponse":
        status = EvidenceProcessingStatus(item.processing_status)
        return cls(
            id=item.id,
            case_id=item.case_id,
            category=EvidenceCategory(item.category),
            display_name=item.display_name,
            lifecycle_status=item.lifecycle_status,
            processing_status=status,
            failure_code=run.failure_code if run else None,
            failure_reason=run.failure_summary if run else None,
            page_count=text.page_count if text else None,
            pages_read=text.pages_read if text else None,
            character_count=text.character_count if text else None,
            text_truncated=text.truncated if text else False,
            can_retry=status in RETRYABLE_STATUSES,
            media_type=file.media_type,
            size_bytes=file.size_bytes,
            original_filename=file.original_filename,
            uploaded_at=file.uploaded_at,
            created_at=item.created_at,
            revision=item.revision,
        )


class EvidenceLibraryResponse(BaseModel):
    """The case's evidence, and the vocabulary the client needs to offer an upload.

    `supported_media_types` is served rather than hard-coded in the frontend so the
    accept-list and the server's allowlist cannot drift into disagreeing about what is
    uploadable — the client would otherwise offer a type the server refuses.
    """

    items: list[EvidenceResponse]
    supported_media_types: list[str] = Field(default_factory=lambda: list(SUPPORTED_MEDIA_TYPES))
    max_upload_bytes: int


class EvidenceContentResponse(BaseModel):
    """A short-lived URL for the file itself.

    Returned as JSON rather than as a 302 so the client controls navigation, and so the
    URL never lands in a browser's address bar or `Referer` where a signed URL would
    outlive the click (threat model §6.4 forbids logging signed URLs; a redirect puts one
    in the history).
    """

    url: str
    expires_in_seconds: int
