"""The worker's tasks.

Two of them, and the difference between them is the whole point of this milestone:

- **`worker.outbox.relay`** runs *without* a tenant. It is infrastructure and must see
  every case, which is why it is allowlisted in `tests/security/test_task_tenant_wiring.py`
  — and why it does nothing but dispatch. It reads no domain row and touches no storage.
- **`worker.evidence.validate`** runs *inside* a tenant, established by `case_task` from
  the database rather than from its own arguments. Every task that touches case-scoped
  data must be built this way, and the harness fails the build for any that is not.

Task arguments carry identifiers only. They travel through Redis, which is
unauthenticated in local compose and published to the host, so a `user_id` in a payload
would be an RLS bypass by message forgery.
"""

import uuid
from typing import Any

import structlog
from celery import Task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.core.storage import StorageError, get_storage
from app.evidence import processing, purge
from app.evidence.domain import ProcessingFailureCode
from app.shared import outbox
from app.shared.db import get_sessionmaker
from app.shared.tenant import set_tenant
from worker.celery_app import celery_app
from worker.context import (
    CaseNoLongerWritable,
    EvidenceNoLongerPresent,
    case_task,
    resolve_evidence_owner,
    tenant_scoped,
)

_log = structlog.get_logger()

#: How many times a transient failure is retried before the run is abandoned.
MAX_RETRIES = 3

#: Base for the exponential backoff, in seconds: 2, 4, 8.
_BACKOFF_BASE = 2


@celery_app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="worker.outbox.relay")
def relay_outbox() -> dict[str, int]:
    """Dispatch undelivered outbox rows. Runs on beat, every second.

    Deliberately tenantless — see the module docstring. The session is opened without
    `set_tenant`, which is the only place in the system that is correct.
    """
    with get_sessionmaker()() as session:
        outcome = outbox.relay_batch(session, _dispatch)
        # Commit *after* the dispatches: `published_at` must not become durable before
        # the broker has the task, or a crash between them loses the job silently.
        session.commit()

    if outcome.dispatched or outcome.failed:
        _log.info(
            "outbox.relayed",
            dispatched=outcome.dispatched,
            declined=outcome.declined,
            failed=outcome.failed,
        )
    return {
        "dispatched": outcome.dispatched,
        "declined": outcome.declined,
        "failed": outcome.failed,
    }


def _dispatch(task_name: str, kwargs: dict[str, object]) -> None:
    celery_app.send_task(task_name, kwargs=kwargs)


def _owner_for(session: Session, evidence_item_id: uuid.UUID) -> str | None:
    """The tenant for the abandon path, resolved the same way as everywhere else.

    Separate from `case_task` because abandoning happens *after* the context manager has
    unwound, and re-entering it would re-check case writability — a case deleted while
    the retries ran would then skip the correction and leave the document mid-flight,
    which is the exact state this path exists to clear.
    """
    try:
        owner, _case_id, _lifecycle = resolve_evidence_owner(session, evidence_item_id)
    except EvidenceNoLongerPresent:
        return None
    return owner


# `tenant_scoped` is the **outer** decorator, and the order is load-bearing: applied
# inside, it stamps the plain function, which `celery_app.task` then wraps in a `Task`
# object the harness cannot see through. The mark has to land on the registered task,
# because that is what `celery_app.tasks` hands the harness. Written the other way round
# first, and caught by `test_a_known_case_scoped_task_is_seen_by_the_check`.
@tenant_scoped
@celery_app.task(bind=True, name="worker.evidence.validate", max_retries=MAX_RETRIES)
def validate_evidence(
    self: Task,
    *,
    outbox_event_id: str,
    aggregate_id: str,
    trace_id: str | None = None,
    evidence_file_id: str | None = None,
    **_: Any,
) -> dict[str, object]:
    """Check an uploaded document's bytes against the type it claimed to be.

    The `outbox_event_id` is the idempotency key: making the delivery identity the
    idempotency identity means a redelivery does nothing and a user-initiated retry —
    which writes a *new* outbox row — gets a genuinely new run.
    """
    evidence_item_id = uuid.UUID(aggregate_id)
    structlog.contextvars.bind_contextvars(trace_id=trace_id)

    try:
        with case_task(evidence_item_id) as ctx:
            outcome = processing.validate_evidence(
                ctx.session,
                get_storage(),
                evidence_item_id=evidence_item_id,
                idempotency_key=outbox_event_id,
                trace_id=trace_id,
                evidence_file_id=uuid.UUID(evidence_file_id) if evidence_file_id else None,
            )
    except SoftTimeLimitExceeded:
        # The bound that slice 3 added, and the trap that came with it. A child killed by
        # the soft time limit — or by `worker_max_memory_per_child` on the next task —
        # leaves the item in `EXTRACTING_TEXT`, which is not retryable, so the user
        # watches "Reading" for good with no control. That is the stranded document again,
        # arriving through the door the resource limits opened.
        #
        # Not retried: a document that exhausted a bound once will exhaust it again, and
        # three more attempts is three more chances to take a worker down. It becomes a
        # terminal failure the user *can* retry deliberately, which is a different thing
        # from retrying it for them.
        with get_sessionmaker()() as session:
            owner = _owner_for(session, evidence_item_id)
            if owner is not None:
                set_tenant(session, owner)
                processing.abandon_run(
                    session,
                    idempotency_key=outbox_event_id,
                    code=ProcessingFailureCode.RESOURCE_LIMIT,
                    summary="This document was too large or too slow to read.",
                )
        _log.warning(
            "evidence.validate_abandoned",
            reason="resource_limit",
            evidence_item_id=str(evidence_item_id),
        )
        return {"failed": True, "reason": "resource_limit"}
    except processing.TransientProcessingError as exc:
        # Retried by hand rather than with `autoretry_for`, because the interesting
        # moment is the *last* one. `autoretry_for` re-raises when the retries run out,
        # and the task simply ends — leaving the run RUNNING and the document showing
        # "Validating" with nothing left in the system that will ever move it. The user
        # watches a state that cannot resolve and the client polls it for as long as the
        # tab is open. So exhaustion is a state transition, not an exception.
        if self.request.retries < MAX_RETRIES:
            raise self.retry(
                exc=exc, countdown=_BACKOFF_BASE ** (self.request.retries + 1)
            ) from exc

        with get_sessionmaker()() as session:
            owner = _owner_for(session, evidence_item_id)
            if owner is not None:
                set_tenant(session, owner)
                processing.abandon_run(
                    session,
                    idempotency_key=outbox_event_id,
                    code=ProcessingFailureCode.STORAGE_UNAVAILABLE,
                    summary="We could not read this file. You can try again.",
                )
        _log.warning(
            "evidence.validate_abandoned",
            reason="transient_failure_retries_exhausted",
            evidence_item_id=str(evidence_item_id),
            attempts=self.request.retries + 1,
        )
        return {"failed": True, "reason": "storage_unavailable"}
    except CaseNoLongerWritable as stop:
        # Not a failure and not a retry: no number of attempts makes a deleted case
        # writable, and a FAILED run would open a PROCESSING_FAILURE issue telling the
        # user their document could not be processed when they deleted the case.
        _log.info(
            "evidence.validate_cancelled",
            reason="case_not_writable",
            lifecycle_status=stop.lifecycle_status,
            evidence_item_id=str(evidence_item_id),
        )
        return {"cancelled": True, "reason": "case_not_writable"}
    except (EvidenceNoLongerPresent, processing.EvidenceNotProcessable):
        _log.info(
            "evidence.validate_cancelled",
            reason="evidence_absent",
            evidence_item_id=str(evidence_item_id),
        )
        return {"cancelled": True, "reason": "evidence_absent"}
    except Exception as exc:
        # The catch-all exists because of what its absence costs. Anything unnamed above
        # left `run.status = RUNNING` and the item in `EXTRACTING_TEXT` — a state that is
        # in neither the terminal set nor the retryable one, so the client polls forever
        # and the retry button answers 409. No user or system recovery existed. An
        # unexpected error should leave a document a person can act on, and then be
        # re-raised so it is visible rather than swallowed.
        with get_sessionmaker()() as session:
            owner = _owner_for(session, evidence_item_id)
            if owner is not None:
                set_tenant(session, owner)
                processing.abandon_run(
                    session,
                    idempotency_key=outbox_event_id,
                    code=ProcessingFailureCode.CORRUPT_FILE,
                    summary="Something went wrong reading this file. You can try again.",
                )
        # The class name, not the exception. `_log.exception` renders the message, and a
        # SQLAlchemy `StatementError` renders `[SQL: ...] [parameters: ...]` — which on
        # this pipeline means a document's extracted text, or the classifier's reasoning,
        # in full, in a log aggregator. `hide_parameters` covers the driver's own
        # rendering and not this one.
        #
        # The traceback is what makes an unexpected error diagnosable, and it is kept:
        # `exc_info` gives frames and line numbers without the exception's own string.
        _log.error(
            "evidence.validate_errored",
            evidence_item_id=str(evidence_item_id),
            error_class=type(exc).__name__,
            exc_info=False,
        )
        raise
    finally:
        structlog.contextvars.unbind_contextvars("trace_id")

    return {
        "run_id": str(outcome.run_id),
        # The *domain* state, never the Celery one. The API projects this vocabulary and
        # nothing else (MVP §8.9).
        "processing_status": outcome.processing_status.value if outcome.processing_status else None,
        "failure_code": outcome.failure_code.value if outcome.failure_code else None,
        "already_done": outcome.already_done,
    }


@tenant_scoped
@celery_app.task(bind=True, name="worker.evidence.purge", max_retries=MAX_RETRIES)
def purge_evidence(
    self: Task,
    *,
    outbox_event_id: str,
    aggregate_id: str,
    trace_id: str | None = None,
    **_: Any,
) -> dict[str, object]:
    """Destroy a deleted document's content (§51.1 steps 3 and 7).

    The relay's **second** consumer, which is the point of it being a relay: the dispatch
    machinery, the tenant acquisition and the at-least-once contract were all built for
    validation, and this reuses every part of them without a line of new plumbing.

    No idempotency key, unlike `validate_evidence`. There is no run row to short-circuit
    and nothing to create twice: object deletion is idempotent in S3 by design, and the
    tombstone is a set of clears that a second pass finds already done. `purge_evidence`
    reads the lifecycle state and returns early on the redelivery.
    """
    evidence_item_id = uuid.UUID(aggregate_id)
    structlog.contextvars.bind_contextvars(trace_id=trace_id)

    try:
        # `allow_terminal_case`: destroying content is what a deleted case is *for*, so a
        # case deletion must not cancel a purge the user already asked for. This branch
        # previously deferred to a case-deletion consumer that `NO_CONSUMER` documents as
        # M11 — the bytes were not handed over, they were abandoned, with no log line.
        with case_task(evidence_item_id, allow_terminal_case=True) as ctx:
            outcome = purge.purge_evidence(
                ctx.session,
                get_storage(),
                evidence_item_id=evidence_item_id,
                trace_id=trace_id,
            )
    except EvidenceNoLongerPresent:
        # The row is gone outright rather than tombstoned, so there is no storage key left
        # to act on and nothing to report. Distinct from the case being deleted, which is
        # now purged normally above.
        return {"purged": False, "reason": "evidence_absent"}
    except StorageError as exc:
        # Transient by assumption — an unreachable store, not a refused delete. The item
        # stays DELETION_PENDING, which is the honest incomplete state: unreachable
        # document, nothing depending on it, bytes still present. Retrying is safe because
        # deleting an absent key is a no-op.
        _log.warning(
            "evidence.purge_deferred",
            evidence_item_id=aggregate_id,
            trace_id=trace_id,
        )
        try:
            raise self.retry(
                exc=exc, countdown=_BACKOFF_BASE ** (self.request.retries + 1)
            ) from exc
        except MaxRetriesExceededError:
            # The interesting moment is the last one, exactly as it is for validation.
            # Past here nothing retries and the user cannot see the item at all — it is
            # already unreachable — so this line is the *only* record that content the
            # user asked to destroy is still in the bucket. `storage_key` is retained on
            # the tombstone for precisely this: an operator can act on this log.
            _log.error(
                "evidence.purge_abandoned",
                evidence_item_id=aggregate_id,
                retries=self.request.retries,
                trace_id=trace_id,
            )
            raise
    finally:
        # Unbind, or a prefork child stamps this trace_id on whatever task it picks up
        # next — `relay_outbox` binds nothing, so one case's id would be attached to
        # another case's log lines. `validate_evidence` does the same for the same reason.
        structlog.contextvars.unbind_contextvars("trace_id")

    return {"purged": outcome.purged, "reason": outcome.reason}
