"""Worker tasks. Just a connectivity ping for now; real pipelines arrive at M7."""

from worker.celery_app import celery_app


@celery_app.task(name="worker.ping")
def ping() -> str:
    return "pong"
