from worker.celery_app import celery_app
from worker.tasks import ping


def test_ping_runs_eagerly() -> None:
    """Eager mode runs the task in-process — proves the task is wired, no broker."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    result = ping.delay()

    assert result.get() == "pong"


def test_the_worker_never_sizes_itself_from_the_cpu_count() -> None:
    """Unset, Celery forks one child per visible CPU. On Railway that was the host's CPUs,
    and the idle children held a flat 4 GB, most of the month's bill. The pool size is a
    setting, and its default is one child."""
    assert celery_app.conf.worker_concurrency == 1
