import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import app.tasks
from app.github_webhook import router, extract_pr_event
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_extract_pr_event():
    body = {
        "action": "opened",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 123, "head": {"sha": "abcdef"}, "body": "This is a fix. /codemind level=2"}
    }
    extracted = extract_pr_event(body, "pull_request")
    assert extracted["owner"] == "owner"
    assert extracted["repo"] == "repo"
    assert extracted["pr_number"] == 123
    assert extracted["head_sha"] == "abcdef"
    assert extracted["level"] == 2

def test_extract_issue_comment_event():
    body = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 456},
        "comment": {"body": "/codemind level=1"}
    }
    extracted = extract_pr_event(body, "issue_comment")
    assert extracted["owner"] == "owner"
    assert extracted["repo"] == "repo"
    assert extracted["pr_number"] == 456
    assert extracted["action"] == "manual_trigger"
    assert extracted["level"] == 1
    assert extracted["head_sha"] == ""

@patch("app.github_webhook.verify_signature")
@patch("app.github_webhook.redis_client.set", new_callable=AsyncMock)
def test_github_webhook_duplicate(mock_redis_set, mock_verify):
    mock_verify.return_value = True
    mock_redis_set.return_value = None  # Lock taken
    
    body = {
        "action": "opened",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 123, "head": {"sha": "abcdef"}}
    }
    headers = {
        "x-github-event": "pull_request",
        "x-hub-signature-256": "sha256=fake",
    }
    
    res = client.post("/api/v1/github/webhook", json=body, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"accepted": True, "reason": "Duplicate webhook running or already processed"}

@patch("app.github_webhook.verify_signature")
@patch("app.github_webhook.redis_client.set", new_callable=AsyncMock)
@patch("app.github_webhook.create_pool", new_callable=AsyncMock)
def test_github_webhook_success(mock_create_pool, mock_redis_set, mock_verify):
    mock_verify.return_value = True
    mock_redis_set.return_value = True  # Lock acquired
    
    mock_pool = AsyncMock()
    mock_create_pool.return_value = mock_pool

    body = {
        "action": "opened",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 123, "head": {"sha": "abcdef"}}
    }
    headers = {
        "x-github-event": "pull_request",
        "x-hub-signature-256": "sha256=fake",
    }
    
    res = client.post("/api/v1/github/webhook", json=body, headers=headers)
    assert res.status_code == 200
    assert "PR review deferred" in res.json()["message"]
    mock_pool.enqueue_job.assert_called_once()
