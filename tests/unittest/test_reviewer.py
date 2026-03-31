import pytest
import asyncio
from unittest.mock import patch, MagicMock

from app.config import Settings
from app.tools.pr_reviewer import PRReviewer

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
        log_level="INFO"
    )

@pytest.fixture
def event_payload():
    return {
        "owner": "test_owner",
        "repo": "test_repo",
        "pr_number": 42
    }

@pytest.fixture
def pr_reviewer(settings, event_payload):
    with patch("app.tools.pr_reviewer.GitHubProvider"):
        with patch("app.tools.pr_reviewer.LiteLLMAIHandler"):
            return PRReviewer(settings, event_payload)

@pytest.mark.asyncio
@patch("app.tools.pr_reviewer.tomllib")
@patch("app.tools.pr_reviewer.Template")
@patch("app.tools.pr_reviewer.LiteLLMAIHandler")
@patch("app.tools.pr_reviewer.GitHubProvider")
async def test_run_multi_agent_concurrency(mock_github_client, mock_ai_handler, mock_template, mock_tomllib, settings, event_payload):
    # Mocking GitHub API
    mock_gh_instance = mock_github_client.return_value
    mock_gh_instance.get_pr_info.return_value = {
        "title": "Fix bug",
        "body": "Fix off by one error",
        "head": {"ref": "fix-branch"},
        "base": {"ref": "main"}
    }
    mock_gh_instance.list_pr_files.return_value = [
        {"filename": "test.py", "patch": "- old\n+ new"}
    ]
    
    # Mocking AI Async Task (Gather)
    mock_ai_instance = mock_ai_handler.return_value
    
    # Needs to return tuples of (content, finish_reason)
    async def mock_async_completion(*args, **kwargs):
        user = args[1]
        if "Mocked Reducer User Prompt" in str(user):
            return "```yaml\nsummary: All good\nestimated_effort: 1\n```", "stop"
        return "Expert Review Result", "stop"
    
    mock_ai_instance.async_chat_completion.side_effect = mock_async_completion
    
    # Mocking TOML Loading
    mock_tomllib.load.return_value = {
        "pr_review_prompt": {
            "system": "Mocked System Prompt",
            "user": "Mocked User Prompt"
        }
    }
    
    # Mocking Template
    def mock_render(*args, **kwargs):
        if "security_report" in kwargs:
            return "Mocked Reducer User Prompt"
        return "Mocked Expert User Prompt"
        
    mock_template.return_value.render.side_effect = mock_render
    
    # Create reviewer manually to inject mocked instances properly
    reviewer = PRReviewer(settings, event_payload)
    reviewer.github = mock_gh_instance
    reviewer.ai = mock_ai_instance
    
    await reviewer.run()
    
    # Verify GitHub info was pulled
    mock_gh_instance.get_pr_info.assert_called_once_with("test_owner", "test_repo", 42)
    mock_gh_instance.list_pr_files.assert_called_once_with("test_owner", "test_repo", 42)
    
    # Reviewer runs 3 concurrent expert prompts + 1 reducer prompt = 4 AI calls total
    assert mock_ai_instance.async_chat_completion.call_count == 4
    
    # Verify the comment was sent to GitHub
    mock_gh_instance.publish_pr_comment.assert_called_once()
    args, kwargs = mock_gh_instance.publish_pr_comment.call_args
    assert "All good" in args[3], "Summary from reducer should be in the final comment"
    assert "CodeMind PR Review" in args[3]

def test_format_review_comment(pr_reviewer):
    raw_response = '''```yaml
estimated_effort: 3
summary: "Overall good but has some logic issues."
security_concerns: "SQL Injection risk on line 42"
performance_concerns: "O(N^2) loop found"
style_concerns: "Missing docstrings"
key_issues_to_review:
  - "Unescaped user input"
```'''
    
    formatted = pr_reviewer._format_review_comment(raw_response)
    
    assert "**得分 (Estimated Effort):** 3/5" in formatted
    assert "Overall good but has some logic issues." in formatted
    assert "SQL Injection risk" in formatted
    assert "O(N^2)" in formatted
    assert "Unescaped user input" in formatted

    # Test failure mode
    bad_yaml = "not yaml format"
    with pytest.raises(Exception):
        pr_reviewer._format_review_comment(bad_yaml, raise_on_fail=True)
