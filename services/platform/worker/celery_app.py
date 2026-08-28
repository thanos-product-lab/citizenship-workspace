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
- **A worker that cannot reach its broker at startup dies.** See below; this is the one
  setting here that exists because of a production incident rather than a design choice.
"""

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (kept for the M8 spend-report task)
from celery.signals import beat_init, worker_init, worker_process_init

from app.core.config import check_backing_services, get_settings
from app.core.logging import configure_logging

# The worker's equivalent of `check_upload_secret` in `create_app`: fail at import, with
# the message at the top of a short traceback, rather than inside a retry loop. A worker
# has no health check for a platform to poll — nothing else would ever notice.
check_backing_services()

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

# A broker that is not there at boot is a configuration error, not a slow dependency.
#
# Celery's default is to retry startup forever, which is the right instinct for a blip
# and precisely wrong for a misconfiguration: the process stays alive, the platform
# reports it healthy, and the only evidence is a log line repeating every 32 seconds. A
# worker has nothing else to report with — no health endpoint, no readiness probe — so
# "alive" is the whole of its status signal, and retrying forever spends it on a lie.
#
# Dying instead lets the platform's restart policy do the work it is for: the service
# crash-loops, which is visible on the canvas without opening anything. Unlike
# `check_backing_services`, this needs no environment variable to be right in order to
# fire, which is why it is the primary guard and that one is the second.
#
# Runtime reconnection is left alone (`broker_connection_retry` stays on). A broker that
# vanishes mid-life *is* a transient dependency, and the tasks are idempotent precisely
# so reconnecting is safe. The distinction is startup versus steady state, not whether
# Redis is allowed to hiccup.
celery_app.conf.broker_connection_retry_on_startup = False

# Nothing may hold a slot indefinitely. boto3 alone defaults to 60s connect and 60s read
# with three attempts, so a single hung ranged GET can occupy the one prefetch slot for
# minutes with `acks_late` on. The soft limit raises an exception the task can still
# record a state from; the hard limit kills the child. Slice 3's PDF parse is the reason
# this belongs on the app rather than on one task.
celery_app.conf.task_soft_time_limit = 60
celery_app.conf.task_time_limit = 90

# Recycle a child that has grown, rather than letting it grow until the container dies.
#
# A page cap does not bound a decompression bomb: those blow up on `open()` or on a
# single page, before any counting happens. Malware scanning is a documented non-goal
# (threat model §7, §28) — resource exhaustion is not. So the answer is that the *child*
# dies and is replaced, which costs one task, instead of the box dying, which costs every
# task and the queue with it. In kilobytes, per Celery's units.
celery_app.conf.worker_max_memory_per_child = 400_000

# And a child is replaced after this many tasks regardless, so a slow leak in a C parser
# cannot accumulate across a long-lived worker.
celery_app.conf.worker_max_tasks_per_child = 100

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


@beat_init.connect
@worker_init.connect
@worker_process_init.connect
def _configure_worker_logging(**_kwargs: object) -> None:
    """Give the worker the same structured logging the API has.

    It had none: `configure_logging` was called from `create_app`, which a worker never
    runs, so every worker line went out through Celery's own default formatting. That
    matters beyond tidiness — the PII discipline in this project is enforced at call
    sites that assume structlog's key/value rendering, and a worker is where document
    filenames and storage keys actually live.

    Connected to three signals, not one. `worker_process_init` is **prefork-only**, so
    under `--pool=solo` or `--pool=threads` — which is what people reach for when
    debugging on macOS — it never fires, and neither does it in the `beat` container.
    Configuring logging on only the pool you expect to run is configuring it for the
    environment where you were not looking.
    """
    configure_logging(get_settings())
