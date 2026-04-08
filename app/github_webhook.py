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
    logger.info(f"extract_pr_event received event type: {event}")
    if event == "check_run":
        action = body.get("action", "")
        logger.info(f"check_run action: {action}")
        if action != "completed":
            return None
        repo_full_name = body.get("repository", {}).get("full_name", "")
        if "/" not in repo_full_name:
            return None
        owner, repo = repo_full_name.split("/", 1)
        
        # A check_run event usually contains check_run.head_sha
        head_sha = body.get("check_run", {}).get("head_sha", "")
        
        return {
            "type": "check_run",
            "owner": owner,
            "repo": repo,
            "action": action,
            "head_sha": head_sha,
        }

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
        "type": "pull_request",
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
    logger.info("=== GitHub Webhook 接收 ===")
    logger.info(f"事件类型: {x_github_event}")
    logger.info(f"交付ID: {x_github_delivery}")
    
    raw_body = await request.body()
    logger.info(f"原始body长度: {len(raw_body)} 字节")

    try:
        verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret)
        logger.info("签名验证通过")
    except WebhookValidationError as e:
        logger.warning(f"Webhook签名验证失败: {e}")
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        body = json.loads(raw_body.decode("utf-8"))
        logger.info(f"解析JSON成功，action字段: {body.get('action', 'N/A')}")
    except Exception as exc:
        logger.error(f"JSON解析失败: {exc}")
        raise HTTPException(status_code=400, detail="invalid json") from exc

    event_payload = extract_pr_event(body, x_github_event)
    logger.info(f"提取的事件payload: {event_payload}")
    
    if not event_payload:
        logger.info(f"事件被忽略: {x_github_event}")
        return {"accepted": False, "reason": f"event ignored: {x_github_event}"}

    if x_github_delivery:
        event_payload["delivery_id"] = x_github_delivery

    event_type = event_payload.get("type")
    owner = event_payload["owner"]
    repo = event_payload["repo"]
    head_sha = event_payload.get("head_sha", "")
    
    logger.info(f"事件类型: {event_type}, owner={owner}, repo={repo}, head_sha={head_sha}")

    # 处理 PR Review 事件
    if event_type == "pull_request":
        pr_number = event_payload["pr_number"]
        lock_key = f"codemind:pr_lock:{owner}:{repo}:{pr_number}:{head_sha}"
        logger.info(f"PR事件锁键: {lock_key}")
        
        is_locked = await redis_client.set(lock_key, "locked", ex=600, nx=True)
        if not is_locked:
            logger.warning(f"重复的webhook或正在处理中: {lock_key}, 忽略")
            return {"accepted": True, "reason": "Duplicate webhook running or already processed"}

        logger.info("处理PR事件payload: %s", event_payload)
        
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        arq_pool = await create_pool(redis_settings)
        
        event_payload["lock_key"] = lock_key
        await arq_pool.enqueue_job("process_pr_review", event_payload)
        logger.info("PR审查任务已加入ARQ队列")
        return {"accepted": True, "message": "PR review deferred to background task via ARQ"}

    # 处理 CI Check Run 完成事件
    elif event_type == "check_run":
        lock_key = f"codemind:ci_lock:{owner}:{repo}:{head_sha}"
        logger.info(f"CI事件锁键: {lock_key}")
        
        is_locked = await redis_client.set(lock_key, "locked", ex=120, nx=True)
        if not is_locked:
            logger.warning(f"重复的check_run webhook或正在处理中: {lock_key}, 忽略")
            return {"accepted": True, "reason": "Duplicate webhook running"}

        logger.info("处理check_run事件payload: %s", event_payload)
        
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        arq_pool = await create_pool(redis_settings)
        
        event_payload["lock_key"] = lock_key
        # We will enqueue this as a new job for ARQ to process
        await arq_pool.enqueue_job("process_ci_result", event_payload, _defer_by=5)
        logger.info("CI结果处理任务已加入ARQ队列，延迟5秒")
        
        return {"accepted": True, "message": "CI result process deferred to ARQ"}

    logger.warning(f"未处理的事件类型: {event_type}")
    return {"accepted": False, "reason": "Unhandled event type"}
