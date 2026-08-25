"""The outbox reader: the half of Domain §40 that M2 deferred.

M2 shipped the outbox write-only, so that a command could never commit business state
and lose the background job that state implies. This is the reader, and it makes three
promises that every consumer has to be built against.

**At-least-once, never exactly-once.** `published_at` is set *after* the broker accepts
the task, so a crash between the two redelivers. The alternative is a distributed
transaction across Postgres and Redis, which we do not have and will not build. A
consumer that cannot tolerate a repeat is a broken consumer — hence
`evidence_processing_runs.idempotency_key`, which is the outbox row's own id.

**No ordering across aggregates.** Rows are claimed in `(created_at, id)` order, but
Celery gives no execution-order guarantee, so two tasks dispatched in order can run in
either. Consumers must be order-independent, and the way processing achieves that is by
carrying `evidence_file_id` in the dispatch: the task acts on the version the event was
about, not on whatever is newest when it happens to run (§16.2).

**A row is delivered or explicitly declined, never silently skipped.** An event type
with no handler is marked published and logged once, because leaving it would hand every
future pass a queue of work it must decline forever — and bury a genuinely undelivered
row in the noise. Which types have no consumer is a decision recorded in `NO_CONSUMER`,
and `tests/shared/test_outbox.py` derives the full set of event types from the
`DomainEvent` subclasses, so a new event forces that decision at the moment it is added
rather than at the moment someone notices nothing happened.

The relay itself runs **without a tenant**. It is infrastructure and must see every
case, which is why it is in `TENANT_FREE_TASKS` — and why it does nothing but dispatch:
it never reads a domain row, never touches storage, and passes only identifiers forward.
Establishing the tenant is the consuming task's job (`worker/context.py`).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.records import OutboxEventRecord

_log = structlog.get_logger()

#: How many rows one pass claims. Small enough that a stuck batch is cheap to redo.
DEFAULT_BATCH = 50

#: `event_type` -> the Celery task that consumes it.
HANDLERS: dict[str, str] = {
    "EvidenceUploaded": "worker.evidence.validate",
    # The same consumer. A retry differs from an upload only in that its outbox row is
    # new — which is precisely what stops the idempotency key short-circuiting it.
    "EvidenceProcessingRequested": "worker.evidence.validate",
}

#: Event types with no consumer, and never a mistake. Each is a fact worth recording in
#: `domain_events` for history and provenance, with no asynchronous work implied. Moving
#: a name out of here into `HANDLERS` is what "we now do something about this" looks like.
NO_CONSUMER: frozenset[str] = frozenset(
    {
        # Case and route lifecycle: recorded, acted on synchronously.
        "CaseCreated",
        "RouteSupportEvaluated",
        "RouteProfileDraftSaved",
        "RouteProfileConfirmed",
        # Residence inputs: their consequence is stale propagation, which happens in the
        # same transaction as the change (Domain §41.2), not asynchronously.
        "ProposedApplicationDateSelected",
        "ProposedApplicationDateChanged",
        "TravelRecordCreated",
        "TravelRecordVersionCreated",
        "TravelRecordRemoved",
        # Evidence coverage: same reasoning as the residence inputs above. Attaching or
        # detaching a document stales `residence.travel_consistency` synchronously, in the
        # link change's own transaction. Nothing asynchronous is owed — and in particular
        # nothing re-reads the document, because a link is the user's assertion rather
        # than a request for the machine to check anything (ADR-0021).
        "EvidenceAttachedToTravelRecord",
        "EvidenceDetachedFromTravelRecord",
        # Assessment and issue outcomes: history, not work.
        "AssessmentRunCompleted",
        "AssessmentRunFailed",
        "AssessmentInvalidated",
        "IssuesReconciled",
        "IssueDismissed",
        # Deletion: the purge consumer arrives with evidence deletion in slice 5. Until
        # then this is honestly undone rather than dispatched into a handler that would
        # do nothing.
        "CaseDeletionRequested",
    }
)

#: Signature of the thing that puts a task on the broker. A parameter rather than a
#: direct Celery import so the relay can be tested without a broker, and so this module
#: stays importable by the API process, which has no business importing worker code.
Dispatch = Callable[[str, dict[str, object]], None]


@dataclass
class RelayOutcome:
    dispatched: int = 0
    declined: int = 0
    failed: int = 0
    event_types: list[str] = field(default_factory=list)


def claim_unpublished(session: Session, *, limit: int = DEFAULT_BATCH) -> list[OutboxEventRecord]:
    """Take a batch of undelivered rows, locking them against a second relay.

    `SKIP LOCKED` rather than `NOWAIT` or a plain lock: two relay processes should each
    get useful work rather than one blocking or erroring. Ordered by `(created_at, id)`
    so dispatch order is at least deterministic, without promising anything about
    execution order — see the module docstring.
    """
    stmt = (
        select(OutboxEventRecord)
        .where(OutboxEventRecord.published_at.is_(None))
        .order_by(OutboxEventRecord.created_at, OutboxEventRecord.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(session.execute(stmt).scalars().all())


def relay_batch(
    session: Session, dispatch: Dispatch, *, limit: int = DEFAULT_BATCH
) -> RelayOutcome:
    """Dispatch one batch, and record what happened to each row.

    The commit is the caller's, and it comes after: `published_at` must not become
    durable before the broker has the task, or a crash in between loses the job silently
    — which is the exact failure the outbox exists to prevent.
    """
    outcome = RelayOutcome()
    now = datetime.now(UTC)

    for row in claim_unpublished(session, limit=limit):
        task = HANDLERS.get(row.event_type)

        if task is None:
            if row.event_type not in NO_CONSUMER:
                # Not a crash: an unknown type is still marked published, because
                # retrying it forever helps nobody. But it is loud, because it means an
                # event was added without deciding what consumes it, and the test that
                # should have caught that did not run.
                _log.warning(
                    "outbox.unknown_event_type",
                    event_type=row.event_type,
                    outbox_event_id=str(row.id),
                )
            row.published_at = now
            outcome.declined += 1
            continue

        try:
            dispatch(
                task,
                {
                    # Identifiers only. A task argument travels through Redis, which is
                    # unauthenticated in local compose — so nothing here may be a
                    # credential, and nothing may be the tenant (worker/context.py).
                    "outbox_event_id": str(row.id),
                    "aggregate_id": str(row.aggregate_id),
                    "trace_id": row.trace_id,
                    # The exact version this delivery is about. Without it the consumer
                    # re-reads "the newest file" at execution time, so two out-of-order
                    # deliveries could leave the item carrying the *older* file's
                    # verdict — including `UPLOADED` for a file nothing ever checked.
                    # No re-upload route exists yet, so this is latent; it is carried
                    # now because it is one line now and an ordering bug later.
                    "evidence_file_id": row.payload.get("evidence_file_id"),
                },
            )
        except Exception as exc:
            row.attempt_count += 1
            # Failure class, never the exception's message: a driver or broker error can
            # carry bound parameters, and `last_error` is read by humans, not machines.
            row.last_error = type(exc).__name__[:500]
            outcome.failed += 1
            _log.warning(
                "outbox.dispatch_failed",
                event_type=row.event_type,
                outbox_event_id=str(row.id),
                error_type=type(exc).__name__,
                attempt=row.attempt_count,
            )
            continue

        row.published_at = now
        outcome.dispatched += 1
        outcome.event_types.append(row.event_type)

    # Flush, so the claim is visible to the next `SELECT ... FOR UPDATE` in this
    # transaction. The sessionmaker sets `autoflush=False`, so without this a second
    # pass re-reads `published_at IS NULL` from the database and dispatches the same row
    # again — every batch after the first would redeliver everything the first sent.
    # The commit stays the caller's: `published_at` must not become durable before the
    # broker has the task.
    session.flush()
    return outcome


def known_event_types() -> frozenset[str]:
    """Every event type the relay has a decision recorded for."""
    return frozenset(HANDLERS) | NO_CONSUMER


# `resolve_case_owner` used to live here and was deleted unused. It answered "who owns
# this case?" for any case id, with no authenticated user, no membership check and no
# tenant — an ownership oracle exported from a module the *API process* imports. Its
# docstring also claimed to be "the one read that runs with no tenant established",
# which `worker/context.py` claims of `resolve_evidence_owner`. Two functions each
# documented as the only one of their kind is how the second gets called from a request
# path. There is exactly one such read, and it lives with the worker.
