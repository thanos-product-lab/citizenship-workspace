from worker.celery_app import celery_app
from worker.tasks import ping


def test_ping_runs_eagerly() -> None:
    """Eager mode runs the task in-process — proves the task is wired, no broker."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    result = ping.delay()

    assert result.get() == "pong"
