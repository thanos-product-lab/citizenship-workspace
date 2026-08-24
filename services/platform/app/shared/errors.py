"""Domain-level exceptions shared across modules, with their HTTP mapping.

`register_exception_handlers` wires these onto the FastAPI app so services and
domain objects can raise intent (`ConcurrencyConflict`, `IllegalTransition`)
without importing HTTP concerns.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base for domain-rule violations surfaced to the API layer."""


class ConcurrencyConflict(DomainError):
    """A command supplied a stale revision; the aggregate changed underneath it."""


class IllegalTransition(DomainError):
    """A lifecycle transition was attempted that the state machine forbids."""


class ProfileIncomplete(DomainError):
    """A profile was confirmed before its required answers were all provided."""

    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        super().__init__(f"missing required answers: {', '.join(missing_fields)}")


class CaseNotActive(DomainError):
    """A case-scoped command that needs an assessable case was issued against one
    that is not ACTIVE (still DRAFT/onboarding, archived, or pending deletion).

    Distinct from the ownership 404 on purpose: the case exists and is the caller's,
    it is simply not yet ready for this input. That is a state the user must be able
    to understand and act on (finish onboarding), not one to hide behind "not found".
    Carries a stable `code` so the frontend can route the user back to onboarding."""

    code = "CASE_NOT_ACTIVE"

    def __init__(self, lifecycle_status: str) -> None:
        self.lifecycle_status = lifecycle_status
        super().__init__(f"this action needs an active case; the case is {lifecycle_status}")


class CaseNotAssessable(DomainError):
    """A trusted assessment was requested for an active case that is missing an input a
    trusted run requires — for slice 1, a selected application date. Distinct from
    `CaseNotActive` (still onboarding) and from the ownership 404: the case is active and
    owned, it just cannot be assessed yet. Carries a stable `code` so the frontend can
    send the user to the missing step rather than showing a dead end."""

    code = "CASE_NOT_ASSESSABLE"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class TravelRecordNotFound(DomainError):
    """A travel record referenced by id does not exist in this case. Raised (→ 404)
    rather than leaking existence when the id is unknown *or* belongs to another of
    the user's own cases — RLS hides other tenants, but not the caller's other cases,
    so the case-ownership of a nested object is checked explicitly (Domain §3.1)."""


class CsvImportMalformed(DomainError):
    """A CSV travel import is structurally unusable — no header, missing required
    columns, or no data rows — so no row can be parsed. Distinct from per-row errors:
    there is nothing to correct row-by-row, the file itself is wrong."""


class CsvImportInvalid(DomainError):
    """A CSV import commit was rejected because at least one row failed validation.
    Carries the full per-row diagnostics `payload` (built by the schema layer) so the
    422 response tells the user exactly which rows to fix; nothing is written."""

    code = "CSV_IMPORT_INVALID"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        super().__init__("the CSV has rows that must be corrected before import")


class EvidenceNotFound(DomainError):
    """An evidence item referenced by id is not reachable in this case. Raised (-> 404)
    for an unknown id, one belonging to another of the caller's own cases, one whose
    upload never completed, and one that has been deleted — all indistinguishable, for
    the same reason `TravelRecordNotFound` is: an id must not confirm existence.

    RLS hides other tenants; it does not hide the caller's other cases, so the
    case-ownership of a nested object is checked explicitly (Domain §3.1, §52)."""


class UnsupportedEvidenceType(DomainError):
    """An upload declared a media type outside the supported set. Refused at presign,
    before a byte is written — MVP §8.9, "unsupported file types are rejected before
    processing". The declared type is also bound into the presigned URL's signature, so
    it is the only type the store will accept for that URL."""

    code = "UNSUPPORTED_EVIDENCE_TYPE"

    def __init__(self, media_type: str, supported: tuple[str, ...]) -> None:
        self.media_type = media_type
        self.supported = supported
        super().__init__(f"{media_type} is not a supported document type")


class EvidenceTooLarge(DomainError):
    """An upload exceeded the size ceiling. Checked twice: against the declared size at
    presign, and against the store's own count at completion — a client controls what it
    declares, not what it uploads."""

    code = "EVIDENCE_TOO_LARGE"

    def __init__(self, size_bytes: int, limit_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        super().__init__(f"the file is larger than the {limit_bytes} byte limit")


class InvalidUploadGrant(DomainError):
    """The signed upload token is missing, altered, expired, or for another case.

    A 422 rather than a 403: by the time this is raised the caller has already passed
    `require_case_access`, so it is not an authorisation failure — the token carries
    integrity, not authority. It means the grant cannot be used, and the fix is to start
    the upload again."""

    code = "INVALID_UPLOAD_GRANT"


class EvidenceNotRetryable(DomainError):
    """A retry was asked for on a document that has nothing to retry.

    Either the work is still in flight, or it already succeeded, or — the interesting
    case — the verdict was `UNSUPPORTED`, which is about the *file*. Running the same
    bytes through the same check reaches the same answer, so a retry there would be a
    button that cannot work. The honest action is to upload a different file."""

    code = "EVIDENCE_NOT_RETRYABLE"

    def __init__(self, processing_status: str) -> None:
        self.processing_status = processing_status
        super().__init__(f"a document that is {processing_status} cannot be retried")


class EvidenceUploadIncomplete(DomainError):
    """Completion was called for a reservation whose object is not in the store. The
    presigned URL was issued but never used, or the upload failed. Nothing is recorded:
    an item whose bytes are absent is not evidence."""

    code = "EVIDENCE_UPLOAD_INCOMPLETE"


class StateWithoutEventError(RuntimeError):
    """A unit of work tried to commit business state without emitting a domain event.

    This is a programming error, not a user error — it never reaches the API as a
    handled response; it fails loudly in tests and logs.
    """


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConcurrencyConflict)
    async def _conflict(_request: Request, _exc: ConcurrencyConflict) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "The record changed since you loaded it; reload and retry."},
        )

    @app.exception_handler(IllegalTransition)
    async def _illegal_transition(_request: Request, exc: IllegalTransition) -> JSONResponse:
        # 409: the aggregate is in a state that conflicts with the requested command.
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(CaseNotActive)
    async def _case_not_active(_request: Request, exc: CaseNotActive) -> JSONResponse:
        # 409: the case's lifecycle state conflicts with a command that needs an
        # active case. Not a 404 — the case is real and owned; it is just not ready.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "code": exc.code,
                "lifecycle_status": exc.lifecycle_status,
            },
        )

    @app.exception_handler(CaseNotAssessable)
    async def _case_not_assessable(_request: Request, exc: CaseNotAssessable) -> JSONResponse:
        # 409: the case is active but missing an input a trusted assessment needs.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc), "code": exc.code},
        )

    @app.exception_handler(TravelRecordNotFound)
    async def _travel_record_not_found(
        _request: Request, _exc: TravelRecordNotFound
    ) -> JSONResponse:
        # 404: unknown id, or an id from another case — indistinguishable on purpose.
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Travel record not found"}
        )

    @app.exception_handler(EvidenceNotFound)
    async def _evidence_not_found(_request: Request, _exc: EvidenceNotFound) -> JSONResponse:
        # 404: unknown id, another case's id, an incomplete upload, or a deleted item —
        # indistinguishable on purpose.
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Evidence not found"}
        )

    @app.exception_handler(UnsupportedEvidenceType)
    async def _unsupported_type(_request: Request, exc: UnsupportedEvidenceType) -> JSONResponse:
        # 422: well-formed request for a document this product cannot read.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc), "code": exc.code, "supported": list(exc.supported)},
        )

    @app.exception_handler(EvidenceTooLarge)
    async def _evidence_too_large(_request: Request, exc: EvidenceTooLarge) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": str(exc), "code": exc.code, "limit_bytes": exc.limit_bytes},
        )

    @app.exception_handler(InvalidUploadGrant)
    async def _invalid_upload_grant(_request: Request, exc: InvalidUploadGrant) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": "The upload could not be recorded; try uploading again.",
                "code": exc.code,
            },
        )

    @app.exception_handler(EvidenceNotRetryable)
    async def _not_retryable(_request: Request, exc: EvidenceNotRetryable) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "code": exc.code,
                "processing_status": exc.processing_status,
            },
        )

    @app.exception_handler(EvidenceUploadIncomplete)
    async def _upload_incomplete(_request: Request, exc: EvidenceUploadIncomplete) -> JSONResponse:
        # 409: the reservation is real, the bytes are not there yet.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "The upload did not complete; try uploading again.",
                "code": exc.code,
            },
        )

    @app.exception_handler(CsvImportMalformed)
    async def _csv_malformed(_request: Request, exc: CsvImportMalformed) -> JSONResponse:
        # 422: well-formed request, but the CSV file itself cannot be used.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc), "code": "CSV_IMPORT_MALFORMED"},
        )

    @app.exception_handler(CsvImportInvalid)
    async def _csv_invalid(_request: Request, exc: CsvImportInvalid) -> JSONResponse:
        # 422: some rows failed validation; the payload lists the exact offending rows.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"code": exc.code, **exc.payload},
        )

    @app.exception_handler(ProfileIncomplete)
    async def _profile_incomplete(_request: Request, exc: ProfileIncomplete) -> JSONResponse:
        # 422: the request is well-formed but the profile cannot yet be confirmed.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc), "missing_fields": exc.missing_fields},
        )
