import logging
from app.config import load_settings
from app.tools.pr_reviewer import PRReviewer

logger = logging.getLogger("codemind.tasks")

async def process_pr_review(ctx, event_payload: dict):
    logger.info("Starting async PR review via ARQ for payload: %s", event_payload)
    settings = load_settings()
    
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
