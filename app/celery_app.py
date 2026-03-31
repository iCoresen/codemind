import os
from celery import Celery
from app.config import load_settings

settings = load_settings()

celery_app = Celery(
    "codemind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
