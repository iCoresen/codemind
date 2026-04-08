import logging
from app.config import load_settings
from app.tools.pr_reviewer import PRReviewer
from app.services.ci_updater import CIUpdaterService

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
        if hasattr(reviewer, "github") and hasattr(reviewer.github, "close"):
            await reviewer.github.close()
        if lock_key:
            await getattr(redis_client, "delete")(lock_key)
        if hasattr(redis_client, "aclose"):
            await redis_client.aclose()
        elif hasattr(redis_client, "close"):
            await getattr(redis_client, "close")()

async def process_ci_result(ctx, event_payload: dict):
    logger.info("Starting async CI result processing via ARQ for payload: %s", event_payload)
    settings = load_settings()
    
    import redis.asyncio as redis
    redis_client = redis.from_url(settings.redis_url)
    lock_key = event_payload.get("lock_key")
    provider = None
    
    try:
        from app.git_providers.github_provider import GitHubProvider
        provider = GitHubProvider(settings.github_token)
        
        owner = event_payload.get("owner")
        repo = event_payload.get("repo")
        head_sha = event_payload.get("head_sha")
        
        if not all([owner, repo, head_sha]):
            logger.warning("Missing required fields for CI result processing")
            return
            
        updater = CIUpdaterService(provider)
        await updater.execute(owner, repo, head_sha)

    except Exception as e:
        logger.error("Failed to process CI result update: %s", e)
        raise
    finally:
        if provider:
            await provider.close()
        if lock_key:
            await getattr(redis_client, "delete")(lock_key)
        if hasattr(redis_client, "aclose"):
            await redis_client.aclose()
        elif hasattr(redis_client, "close"):
            await getattr(redis_client, "close")()
