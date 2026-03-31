import asyncio
import logging
from app.celery_app import celery_app
from app.config import load_settings
from app.tools.pr_reviewer import PRReviewer

logger = logging.getLogger("codemind.tasks")

@celery_app.task(bind=True, max_retries=3)
def process_pr_review(self, event_payload: dict):
    logger.info("Starting async PR review via Celery for payload: %s", event_payload)
    settings = load_settings()

    async def run_review():
        import redis.asyncio as redis
        redis_client = redis.from_url(settings.redis_url)
        reviewer = PRReviewer(settings, event_payload)
        lock_key = event_payload.get("lock_key")
        
        try:
            await reviewer.run()
        except Exception as e:
            logger.error("Failed to process PR Review: %s", e)
            raise
        finally:
            if lock_key:
                await getattr(redis_client, "delete")(lock_key)
            if hasattr(redis_client, "aclose"):
                await redis_client.aclose()
            elif hasattr(redis_client, "close"):
                await getattr(redis_client, "close")()

    try:
        asyncio.run(run_review())
    except Exception as exc:
        logger.error("Error during PR review execution: %s", exc)
        raise self.retry(exc=exc, countdown=60)
