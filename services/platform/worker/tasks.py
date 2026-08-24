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

from app.core.storage import get_storage
from app.evidence import processing
from app.shared import outbox
from app.shared.db import get_sessionmaker
from worker.celery_app import celery_app
from worker.context import (
    CaseNoLongerWritable,
    EvidenceNoLongerPresent,
    case_task,
    tenant_scoped,
)

_log = structlog.get_logger()

#: Transient failures are retried with backoff; terminal ones are not (Technical
#: Architecture RFC §18). `TransientProcessingError` is raised only where nothing has
#: been concluded about the file — the store was unreachable, not the document unusable.
_RETRY_FOR = (processing.TransientProcessingError,)


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


# `tenant_scoped` is the **outer** decorator, and the order is load-bearing: applied
# inside, it stamps the plain function, which `celery_app.task` then wraps in a `Task`
# object the harness cannot see through. The mark has to land on the registered task,
# because that is what `celery_app.tasks` hands the harness. Written the other way round
# first, and caught by `test_a_known_case_scoped_task_is_seen_by_the_check`.
@tenant_scoped
@celery_app.task(
    bind=True,
    name="worker.evidence.validate",
    autoretry_for=_RETRY_FOR,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def validate_evidence(
    self: Task, *, outbox_event_id: str, aggregate_id: str, trace_id: str | None = None, **_: Any
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
            )
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
    except (EvidenceNoLongerPresent, LookupError):
        _log.info(
            "evidence.validate_cancelled",
            reason="evidence_absent",
            evidence_item_id=str(evidence_item_id),
        )
        return {"cancelled": True, "reason": "evidence_absent"}
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
