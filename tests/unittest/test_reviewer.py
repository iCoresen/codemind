import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.config import Settings
from app.tools.pr_reviewer import PRReviewer
from app.agents.base_agent import AgentResult, AgentStatus


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
        ai_embedding_model="fake_embedding_model",
        default_review_level=3,
        core_keywords=["auth", "payment", "database"],
    )


@pytest.fixture
def event_payload():
    return {"owner": "test_owner", "repo": "test_repo", "pr_number": 42}


@pytest.mark.asyncio
@patch("app.tools.pr_reviewer.ChangelogAgent")
@patch("app.tools.pr_reviewer.LogicAgent")
@patch("app.tools.pr_reviewer.UnitTestAgent")
@patch("app.tools.pr_reviewer.TimeoutController")
@patch("app.tools.pr_reviewer.GitHubProvider")
@patch.object(PRReviewer, "_extract_ast_signatures", new_callable=AsyncMock)
async def test_run_multi_agent_concurrency(
    mock_extract_ast,
    mock_github_provider,
    mock_timeout_controller,
    mock_ut_agent,
    mock_logic_agent,
    mock_cl_agent,
    settings,
    event_payload,
):
    # Mock GitHub Client behavior
    mock_gh_instance = mock_github_provider.return_value
    mock_gh_instance.get_pr_info = AsyncMock(
        return_value={
            "title": "Fix bug",
            "body": "Fix off by one error",
            "head": {"ref": "fix-branch", "sha": "fake_sha"},
            "base": {"ref": "main"},
        }
    )
    mock_gh_instance.list_pr_files = AsyncMock(
        return_value=[
            {"filename": "test.py", "patch": "- old\n+ new", "status": "modified"}
        ]
    )
    mock_gh_instance.get_pr_commits = AsyncMock(
        return_value=[{"sha": "12345", "message": "commit message", "author": "me"}]
    )
    mock_gh_instance.publish_pr_comment = AsyncMock(return_value=12345)
    mock_gh_instance.update_pr_comment = AsyncMock()

    mock_extract_ast.return_value = "Mock AST Signature"

    # Mock Timeout Controller
    mock_tc_instance = mock_timeout_controller.return_value

    # We need the timeout controller to return mocked results based on the agent it gets
    async def mock_run_with_timeout(agent, context):
        if agent == mock_cl_agent.return_value:
            return AgentResult("changelog", AgentStatus.COMPLETED, "CL Result", 1.0)
        elif agent == mock_logic_agent.return_value:
            return AgentResult("logic", AgentStatus.COMPLETED, "Logic Result", 2.0)
        elif agent == mock_ut_agent.return_value:
            return AgentResult("unittest", AgentStatus.COMPLETED, "UT Result", 3.0)
        return AgentResult("unknown", AgentStatus.FAILED, "Error", 0)

    mock_tc_instance.run_with_timeout = AsyncMock(side_effect=mock_run_with_timeout)

    reviewer = PRReviewer(settings, event_payload)
    reviewer.github = mock_gh_instance
    reviewer.ai = (
        MagicMock()
    )  # Not used directly in the mocked run since agents are mocked

    await reviewer.run()

    # Verify GitHub info was pulled concurrently
    mock_gh_instance.get_pr_info.assert_called_once_with("test_owner", "test_repo", 42)
    mock_gh_instance.list_pr_files.assert_called_once_with(
        "test_owner", "test_repo", 42
    )
    mock_gh_instance.get_pr_commits.assert_called_once_with(
        "test_owner", "test_repo", 42
    )

    # Verify the initial skeleton comment was published
    mock_gh_instance.publish_pr_comment.assert_called_once()

    # Verify timeout controller was called for appropriate agents
    # Based on determine_review_level logic: total_changes < 50 returns Level 2
    # Level 2 activates changelog and logic agents only (not unittest)
    assert mock_tc_instance.run_with_timeout.call_count == 2

    # Verify incremental updates were pushed to GitHub
    # With Level 2 review (changelog + logic agents), we expect at least 2 updates
    assert mock_gh_instance.update_pr_comment.call_count >= 2


def test_logic_agent_format_review_comment():
    # Because we moved this function to logic_agent, we can test it directly there.
    from app.agents.logic_agent import LogicAgent
    from unittest.mock import MagicMock

    settings = MagicMock()
    ai_handler = MagicMock()
    agent = LogicAgent(ai_handler, settings)

    raw_response = """```yaml
final_review:
  executive_summary: "Overall good but has some logic issues."
  metrics:
    estimated_review_effort: 3
    security_score: 5
  prioritized_issues:
    high_priority_issues:
      - title: "Security concerns"
        description: "SQL Injection risk"
        file: "app/models.py"
        line: 42
    medium_priority_issues:
      - title: "Performance concerns"
        description: "O(N^2) loop found"
        file: "app/utils.py"
        line: 100
    low_priority_suggestions:
      - title: "Style concerns"
        description: "Missing docstrings"
        file: "app/utils.py"
        line: 10
```"""

    formatted = agent._format_review_content(
        raw_response, "test_owner", "test_repo", "fake_sha"
    )

    assert "**Estimated effort to review:** 3" in formatted
    assert "Overall good but has some logic issues." in formatted
    assert "SQL Injection risk" in formatted
    assert "O(N^2)" in formatted
