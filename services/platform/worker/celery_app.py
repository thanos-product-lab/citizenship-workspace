"""Celery application, and the settings that make redelivery safe.

Redis is both broker and result backend for the MVP.

Three configuration choices carry weight:

- **`task_acks_late` + `task_reject_on_worker_lost`.** A task is acknowledged after it
  finishes, not when it is picked up, so a worker killed mid-task redelivers rather than
  losing the work. That is only safe because every consumer is idempotent — evidence
  processing keys on `idempotency_key`, which is the outbox row's own id.
- **A bounded prefetch.** Document processing is slow and uneven; a worker that grabs
  four tasks and sits on three of them behind one slow PDF is a worker whose queue depth
  says nothing useful.
- **Beat runs the outbox relay.** The alternative — calling `.delay()` after the command
  commits — reintroduces exactly the lost-job window the outbox exists to close.
"""

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (kept for the M8 spend-report task)
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery(
    "citizenship",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)

celery_app.conf.task_track_started = True
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1

#: How often the relay looks for undelivered outbox rows. A second is short enough that
#: an upload appears to process immediately and long enough that an idle system is not
#: doing meaningful work.
OUTBOX_POLL_SECONDS = 1.0

celery_app.conf.beat_schedule = {
    "outbox-relay": {
        "task": "worker.outbox.relay",
        "schedule": OUTBOX_POLL_SECONDS,
    },
}


@worker_process_init.connect
def _configure_worker_logging(**_kwargs: object) -> None:
    """Give the worker the same structured logging the API has.

    It had none: `configure_logging` was called from `create_app`, which a worker never
    runs, so every worker line went out through Celery's own default formatting. That
    matters beyond tidiness — the PII discipline in this project is enforced at call
    sites that assume structlog's key/value rendering, and a worker is where document
    filenames and storage keys actually live.
    """
    configure_logging(get_settings())
