"""Celery application. Redis is both broker and result backend for the MVP."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "citizenship",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)
celery_app.conf.task_track_started = True
