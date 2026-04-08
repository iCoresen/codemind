import logging
from arq import create_pool
from arq.connections import RedisSettings
from app.config import load_settings
from app.log_config import setup_logging
from app.tasks import process_pr_review

settings = load_settings()
setup_logging(settings, "arq")

logger = logging.getLogger("codemind.arq")

redis_settings = RedisSettings.from_dsn(settings.redis_url)

class WorkerSettings:
    functions = [process_pr_review]
    redis_settings = redis_settings
    max_jobs = 10
    max_tries = 3
    
    async def on_startup(ctx):
        logger.info("ARQ Worker started")

    async def on_shutdown(ctx):
        logger.info("ARQ Worker shutting down")
