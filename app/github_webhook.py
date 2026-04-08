import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings

from app.config import load_settings
from app.exceptions import WebhookValidationError

logger = logging.getLogger("codemind.webhook")
router = APIRouter()
settings = load_settings()

redis_client = redis.from_url(settings.redis_url)

def verify_signature(raw_body: bytes, signature_256: str | None, secret: str) -> bool:
    if not secret:
        return True
    if not signature_256 or not signature_256.startswith("sha256="):
        raise WebhookValidationError("Missing or invalid signature header")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    received = signature_256.replace("sha256=", "", 1)
    if not hmac.compare_digest(expected, received):
        raise WebhookValidationError("Signature verification failed")
    return True


def extract_pr_event(body: dict[str, Any], event: str) -> dict[str, Any] | None:
    if event != "pull_request":
        return None

    action = body.get("action", "")
    if action not in {"opened", "reopened", "synchronize"}:
        return None

    repo_full_name = body.get("repository", {}).get("full_name", "")
    if "/" not in repo_full_name:
        return None

    owner, repo = repo_full_name.split("/", 1)
    pr_number = body.get("pull_request", {}).get("number")
    if not pr_number:
        return None

    head_sha = body.get("pull_request", {}).get("head", {}).get("sha", "")

    # 合格的 event_payload：owner, repo, pr_number, action, head_sha
    return {
        "owner": owner,
        "repo": repo,
        "pr_number": int(pr_number),
        "action": action,
        "head_sha": head_sha,
    }


@router.post("/api/v1/github/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
):
    raw_body = await request.body()

    try:
        verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret)
    except WebhookValidationError as e:
        logger.warning(f"Webhook signature validation failed: {e}")
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc

    event_payload = extract_pr_event(body, x_github_event)
    if not event_payload:
        return {"accepted": False, "reason": "event ignored"}

    if x_github_delivery:
        event_payload["delivery_id"] = x_github_delivery

    owner = event_payload["owner"]
    repo = event_payload["repo"]
    pr_number = event_payload["pr_number"]
    head_sha = event_payload.get("head_sha", "")

    lock_key = f"codemind:pr_lock:{owner}:{repo}:{pr_number}:{head_sha}"
    
    # 尝试获取分布式锁，过期时间 10 分钟 (600s)
    # 使用 Redis nx=True 实现互斥，并利用 asyncio 避免阻塞 FastAPI 的事件循环
    is_locked = await redis_client.set(lock_key, "locked", ex=600, nx=True)
    if not is_locked:
        logger.warning(f"Duplicate webhook or already processing: {lock_key}, ignoring.")
        return {"accepted": True, "reason": "Duplicate webhook running or already processed"}

    logger.info("Processing event payload: %s", event_payload)
    
    # 建立 arq pool
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    arq_pool = await create_pool(redis_settings)
    
    # 调用 ARQ 任务
    event_payload["lock_key"] = lock_key
    await arq_pool.enqueue_job("process_pr_review", event_payload)

    return {"accepted": True, "message": "PR review deferred to background task via ARQ"}
