import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, BackgroundTasks

from app.config import load_settings
from app.tools.pr_reviewer import PRReviewer

logger = logging.getLogger("codemind.webhook")
router = APIRouter()
settings = load_settings()

def verify_signature(raw_body: bytes, signature_256: str | None, secret: str) -> bool:
    if not secret:
        return True
    if not signature_256 or not signature_256.startswith("sha256="):
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    received = signature_256.replace("sha256=", "", 1)
    return hmac.compare_digest(expected, received)


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

    # 合格的 event_payload：owner, repo, pr_number, action
    return {
        "owner": owner,
        "repo": repo,
        "pr_number": int(pr_number),
        "action": action,
    }


@router.post("/api/v1/github/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
):
    raw_body = await request.body()

    if not verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret):
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

    logger.info("[github_webhook] processing event payload=%s", event_payload)
    
    # Process review locally in the background so GitHub gets immediate response
    reviewer = PRReviewer(settings, event_payload)
    background_tasks.add_task(reviewer.run)

    return {"accepted": True}
