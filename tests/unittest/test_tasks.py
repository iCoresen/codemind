import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from app.tasks import process_pr_review
from celery.exceptions import Retry

# Because the task uses getattr(redis_client, "delete"), setting a mock on .delete works.

@patch("app.tasks.load_settings")
@patch("app.tasks.PRReviewer")
@patch("redis.asyncio.from_url")
def test_process_pr_review_success(mock_from_url, mock_pr_reviewer, mock_load_settings):
    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379/0"
    mock_load_settings.return_value = mock_settings
    
    mock_redis_client = MagicMock()
    mock_redis_client.delete = AsyncMock()
    mock_redis_client.aclose = AsyncMock()
    
    mock_from_url.return_value = mock_redis_client
    
    mock_reviewer_instance = MagicMock()
    mock_reviewer_instance.run = AsyncMock()
    mock_pr_reviewer.return_value = mock_reviewer_instance

    payload = {"lock_key": "test_lock", "action": "opened"}
    
    process_pr_review(payload)
    
    mock_load_settings.assert_called_once()
    mock_pr_reviewer.assert_called_once_with(mock_settings, payload)
    mock_reviewer_instance.run.assert_called_once()
    
    mock_redis_client.delete.assert_called_once_with("test_lock")
    mock_redis_client.aclose.assert_called_once()


@patch("app.tasks.load_settings")
@patch("app.tasks.PRReviewer")
@patch("redis.asyncio.from_url")
def test_process_pr_review_exception_retry(mock_from_url, mock_pr_reviewer, mock_load_settings):
    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379/0"
    mock_load_settings.return_value = mock_settings
    
    mock_redis_client = MagicMock()
    mock_redis_client.delete = AsyncMock()
    mock_redis_client.aclose = AsyncMock()
    mock_from_url.return_value = mock_redis_client
    
    mock_reviewer_instance = MagicMock()
    mock_reviewer_instance.run = AsyncMock(side_effect=Exception("Test error"))
    mock_pr_reviewer.return_value = mock_reviewer_instance

    payload = {"lock_key": "some_lock", "action": "opened"}

    with patch.object(process_pr_review, "retry") as mock_retry:
        mock_retry.side_effect = Retry("Retry exception")
        
        with pytest.raises(Retry):
            process_pr_review(payload)
        
        mock_retry.assert_called_once()
        
        mock_redis_client.delete.assert_called_once_with("some_lock")
        mock_redis_client.aclose.assert_called_once()
