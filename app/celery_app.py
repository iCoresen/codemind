import os
from celery import Celery
from app.config import load_settings
from app.log_config import setup_logging

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

# 使用 Celery 的信号在 worker 启动时初始化日志记录器，这样确保不会被默认的 Celery logger 覆盖
from celery.signals import setup_logging as celery_setup_logging
import logging

@celery_setup_logging.connect
def on_celery_setup_logging(**kwargs):
    # 配置我们自定义的日志方案，统一输出到 logs/celery.log
    setup_logging(settings, "celery")

