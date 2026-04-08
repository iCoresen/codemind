import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.tasks import process_pr_review

@pytest.mark.asyncio
@patch("app.tasks.load_settings")
@patch("app.tasks.PRReviewer")
@patch("redis.asyncio.from_url")
async def test_process_pr_review_success(mock_from_url, mock_pr_reviewer, mock_load_settings):
    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379/0"
    mock_load_settings.return_value = mock_settings
    
    mock_redis_client = MagicMock()
    # The code under test uses await getattr(redis_client, "delete"). 
    mock_delete = AsyncMock()
    # We patch getattr for delete directly in the test execution context for ARQ test style
    setattr(mock_redis_client, "delete", mock_delete)
    mock_aclose = AsyncMock()
    setattr(mock_redis_client, "aclose", mock_aclose)
    
    mock_from_url.return_value = mock_redis_client
    
    mock_reviewer_instance = MagicMock()
    mock_reviewer_instance.run = AsyncMock()
    mock_pr_reviewer.return_value = mock_reviewer_instance

    payload = {"lock_key": "test_lock", "action": "opened"}
    
    ctx = {}
    await process_pr_review(ctx, payload)
    
    mock_load_settings.assert_called_once()
    mock_pr_reviewer.assert_called_once_with(mock_settings, payload)
    mock_reviewer_instance.run.assert_called_once()
    
    mock_delete.assert_called_once_with("test_lock")
    mock_aclose.assert_called_once()


@pytest.mark.asyncio
@patch("app.tasks.load_settings")
@patch("app.tasks.PRReviewer")
@patch("redis.asyncio.from_url")
async def test_process_pr_review_exception(mock_from_url, mock_pr_reviewer, mock_load_settings):
    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379/0"
    mock_load_settings.return_value = mock_settings
    
    mock_redis_client = MagicMock()
    mock_delete = AsyncMock()
    setattr(mock_redis_client, "delete", mock_delete)
    mock_aclose = AsyncMock()
    setattr(mock_redis_client, "aclose", mock_aclose)
    mock_from_url.return_value = mock_redis_client
    
    mock_reviewer_instance = MagicMock()
    mock_reviewer_instance.run = AsyncMock(side_effect=Exception("Test error"))
    mock_pr_reviewer.return_value = mock_reviewer_instance

    payload = {"lock_key": "some_lock", "action": "opened"}

    ctx = {}
    with pytest.raises(Exception):
        await process_pr_review(ctx, payload)
        
    mock_delete.assert_called_once_with("some_lock")
    mock_aclose.assert_called_once()
