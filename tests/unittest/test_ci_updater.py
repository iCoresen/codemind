"""
CIUpdaterService 单元测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.ci_updater import CIUpdaterService
from app.git_providers.github_provider import GitHubProvider
from app.agents.result_aggregator import ResultAggregator


@pytest.fixture
def mock_github_provider():
    """模拟 GitHubProvider"""
    mock = MagicMock(spec=GitHubProvider)
    mock._headers = MagicMock(return_value={"Authorization": "Bearer fake_token"})
    return mock


@pytest.fixture
def ci_updater(mock_github_provider):
    """创建 CIUpdaterService 实例"""
    return CIUpdaterService(mock_github_provider)


@pytest.mark.asyncio
async def test_execute_no_pr_found(ci_updater, mock_github_provider):
    """测试没有找到关联 PR 的情况"""
    # 模拟 _get_prs_for_commit 返回空列表
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = []
        
        await ci_updater.execute("owner", "repo", "abc123")
        
        mock_get_prs.assert_called_once_with("owner", "repo", "abc123")
        # 确保没有调用其他方法
        mock_github_provider.get_pr_check_runs.assert_not_called()


@pytest.mark.asyncio
async def test_execute_no_relevant_checks(ci_updater, mock_github_provider):
    """测试没有相关 CI 检查的情况"""
    # 模拟找到 PR
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = [{"number": 1}]
        
        # 模拟没有相关检查
        mock_github_provider.get_pr_check_runs = AsyncMock(return_value=[
            {"name": "build", "status": "completed", "conclusion": "success"}
        ])
        
        await ci_updater.execute("owner", "repo", "abc123")
        
        mock_get_prs.assert_called_once_with("owner", "repo", "abc123")
        mock_github_provider.get_pr_check_runs.assert_called_once_with("owner", "repo", "abc123")


@pytest.mark.asyncio
async def test_execute_checks_still_pending(ci_updater, mock_github_provider):
    """测试 CI 检查仍在进行中的情况"""
    # 模拟找到 PR
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = [{"number": 1}]
        
        # 模拟有 pending 状态的检查
        mock_github_provider.get_pr_check_runs = AsyncMock(return_value=[
            {"name": "flake8", "status": "in_progress", "conclusion": None},
            {"name": "eslint", "status": "queued", "conclusion": None}
        ])
        
        await ci_updater.execute("owner", "repo", "abc123")
        
        mock_get_prs.assert_called_once_with("owner", "repo", "abc123")
        mock_github_provider.get_pr_check_runs.assert_called_once_with("owner", "repo", "abc123")


@pytest.mark.asyncio
async def test_execute_no_bot_comments(ci_updater, mock_github_provider):
    """测试没有找到 CodeMind 评论的情况"""
    # 模拟找到 PR
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = [{"number": 1}]
        
        # 模拟有完成的检查
        mock_github_provider.get_pr_check_runs = AsyncMock(return_value=[
            {"name": "flake8", "status": "completed", "conclusion": "success"}
        ])
        
        # 模拟没有找到 bot 评论
        with patch.object(ci_updater, '_get_bot_comments', new_callable=AsyncMock) as mock_get_comments:
            mock_get_comments.return_value = []
            
            await ci_updater.execute("owner", "repo", "abc123")
            
            mock_get_prs.assert_called_once_with("owner", "repo", "abc123")
            mock_get_comments.assert_called_once_with("owner", "repo", 1)


@pytest.mark.asyncio
async def test_execute_ci_already_appended(ci_updater, mock_github_provider):
    """测试 CI 结果已经追加过的情况"""
    # 模拟找到 PR
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = [{"number": 1}]
        
        # 模拟有完成的检查
        mock_github_provider.get_pr_check_runs = AsyncMock(return_value=[
            {"name": "flake8", "status": "completed", "conclusion": "success"}
        ])
        
        # 模拟找到 bot 评论
        with patch.object(ci_updater, '_get_bot_comments', new_callable=AsyncMock) as mock_get_comments:
            mock_get_comments.return_value = [
                {"id": 123, "body": "CodeMind review...<!-- CI_RESULTS -->Already appended"}
            ]
            
            # 模拟 aggregator 判断已经追加过
            mock_aggregator = MagicMock(spec=ResultAggregator)
            mock_aggregator.has_ci_results = MagicMock(return_value=True)
            ci_updater.aggregator = mock_aggregator
            
            await ci_updater.execute("owner", "repo", "abc123")
            
            mock_get_prs.assert_called_once_with("owner", "repo", "abc123")
            mock_get_comments.assert_called_once_with("owner", "repo", 1)
            mock_aggregator.has_ci_results.assert_called_once()


@pytest.mark.asyncio
async def test_execute_successful_update(ci_updater, mock_github_provider):
    """测试成功更新 CI 结果的情况"""
    # 模拟找到 PR
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = [{"number": 1}]
        
        # 模拟有完成的检查
        mock_github_provider.get_pr_check_runs = AsyncMock(return_value=[
            {"name": "flake8", "status": "completed", "conclusion": "success"},
            {"name": "eslint", "status": "completed", "conclusion": "failure"}
        ])
        
        # 模拟找到 bot 评论
        with patch.object(ci_updater, '_get_bot_comments', new_callable=AsyncMock) as mock_get_comments:
            mock_get_comments.return_value = [
                {"id": 123, "body": "CodeMind review...<!-- CI_RESULTS -->"}
            ]
            
            # 模拟 aggregator 方法
            mock_aggregator = MagicMock(spec=ResultAggregator)
            mock_aggregator.has_ci_results = MagicMock(return_value=False)
            mock_aggregator.append_ci_results = MagicMock(return_value="Updated body with CI results")
            ci_updater.aggregator = mock_aggregator
            
            # 模拟更新评论
            mock_github_provider.update_pr_comment = AsyncMock()
            
            await ci_updater.execute("owner", "repo", "abc123")
            
            mock_get_prs.assert_called_once_with("owner", "repo", "abc123")
            mock_get_comments.assert_called_once_with("owner", "repo", 1)
            mock_aggregator.has_ci_results.assert_called_once()
            mock_aggregator.append_ci_results.assert_called_once()
            mock_github_provider.update_pr_comment.assert_called_once_with(
                "owner", "repo", 123, "Updated body with CI results"
            )


@pytest.mark.asyncio
async def test_execute_multiple_prs(ci_updater, mock_github_provider):
    """测试一个提交关联多个 PR 的情况"""
    # 模拟找到多个 PR
    with patch.object(ci_updater, '_get_prs_for_commit', new_callable=AsyncMock) as mock_get_prs:
        mock_get_prs.return_value = [
            {"number": 1},
            {"number": 2}
        ]
        
        # 模拟有完成的检查
        mock_github_provider.get_pr_check_runs = AsyncMock(return_value=[
            {"name": "flake8", "status": "completed", "conclusion": "success"}
        ])
        
        # 模拟为每个 PR 找到评论
        with patch.object(ci_updater, '_get_bot_comments', new_callable=AsyncMock) as mock_get_comments:
            mock_get_comments.side_effect = [
                [{"id": 123, "body": "CodeMind review PR1"}],
                [{"id": 456, "body": "CodeMind review PR2"}]
            ]
            
            # 模拟 aggregator 方法
            mock_aggregator = MagicMock(spec=ResultAggregator)
            mock_aggregator.has_ci_results = MagicMock(return_value=False)
            mock_aggregator.append_ci_results = MagicMock(return_value="Updated body")
            ci_updater.aggregator = mock_aggregator
            
            # 模拟更新评论
            mock_github_provider.update_pr_comment = AsyncMock()
            
            await ci_updater.execute("owner", "repo", "abc123")
            
            # 验证为两个 PR 都调用了更新
            assert mock_github_provider.update_pr_comment.call_count == 2
            mock_github_provider.update_pr_comment.assert_any_call("owner", "repo", 123, "Updated body")
            mock_github_provider.update_pr_comment.assert_any_call("owner", "repo", 456, "Updated body")


@pytest.mark.asyncio
async def test_get_prs_for_commit_success(ci_updater, mock_github_provider):
    """测试成功获取关联 PR"""
    # 模拟 httpx 响应
    mock_response = MagicMock()
    mock_response.json.return_value = [{"number": 1, "title": "Test PR"}]
    mock_response.raise_for_status = MagicMock()
    
    # 模拟 httpx.AsyncClient 上下文管理器
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    
    with patch('httpx.AsyncClient') as mock_client_class:
        # 模拟 AsyncClient 的上下文管理器行为
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await ci_updater._get_prs_for_commit("owner", "repo", "abc123")
        
        assert result == [{"number": 1, "title": "Test PR"}]
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/commits/abc123/pulls",
            headers={
                "Authorization": "Bearer fake_token"
            },
            timeout=20.0
        )


@pytest.mark.asyncio
async def test_get_prs_for_commit_failure(ci_updater, mock_github_provider):
    """测试获取关联 PR 失败"""
    # 模拟 httpx.AsyncClient 上下文管理器
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("Network error"))
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await ci_updater._get_prs_for_commit("owner", "repo", "abc123")
        
        assert result == []
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/commits/abc123/pulls",
            headers={
                "Authorization": "Bearer fake_token"
            },
            timeout=20.0
        )


@pytest.mark.asyncio
async def test_get_bot_comments_success(ci_updater, mock_github_provider):
    """测试成功获取 bot 评论"""
    mock_comments = [
        {"id": 1, "body": "Regular comment"},
        {"id": 2, "body": "CodeMind review comment"},
        {"id": 3, "body": "Another CodeMind comment"}
    ]
    
    mock_github_provider.get_pr_comments = AsyncMock(return_value=mock_comments)
    
    result = await ci_updater._get_bot_comments("owner", "repo", 1)
    
    assert len(result) == 2
    assert result[0]["id"] == 2
    assert result[1]["id"] == 3
    mock_github_provider.get_pr_comments.assert_called_once_with("owner", "repo", 1)


@pytest.mark.asyncio
async def test_get_bot_comments_failure(ci_updater, mock_github_provider):
    """测试获取评论失败"""
    mock_github_provider.get_pr_comments = AsyncMock(side_effect=Exception("API error"))
    
    result = await ci_updater._get_bot_comments("owner", "repo", 1)
    
    assert result == []
