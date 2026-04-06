import os
import pytest
from unittest.mock import patch, MagicMock
from app.config import Settings
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler

@pytest.fixture
def settings():
    return Settings(
        github_token="fake_token",
        ai_api_key="fake_key",
        ai_model="fake_model",
        ai_base_url="https://fake.api.com",
        ai_fallback_models="fake_fallback",
        ai_timeout=30,
        github_webhook_secret="fake_secret",
        server_host="0.0.0.0",
        server_port=8080,
        log_level="INFO",
        redis_url="redis://localhost:6379/0",
        changelog_soft_timeout=5,
        changelog_hard_timeout=10,
        logic_soft_timeout=15,
        logic_hard_timeout=25,
        unittest_soft_timeout=20,
        unittest_hard_timeout=30,
    )

@pytest.fixture
def ai_handler(settings):
    return LiteLLMAIHandler(settings)

def test_ai_handler_init(settings, ai_handler):
    assert ai_handler.settings.ai_model == "fake_model"
    assert os.environ.get("LITELLM_API_KEY") == "fake_key"

@pytest.mark.asyncio
@patch("app.ai_handlers.litellm_ai_handler.acompletion")
async def test_async_chat_completion(mock_acompletion, ai_handler):
    # Mocking LiteLLM acompletion response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Mocked Async Response"
    mock_response.choices[0].finish_reason = "stop"
    mock_acompletion.return_value = mock_response

    content, finish_reason = await ai_handler.async_chat_completion("System prompt", "User prompt")
    
    assert content == "Mocked Async Response"
    assert finish_reason == "stop"
    mock_acompletion.assert_called_once()
    args, kwargs = mock_acompletion.call_args
    assert kwargs["model"] == "fake_model"
