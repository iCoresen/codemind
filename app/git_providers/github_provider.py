from typing import Any
import httpx

from app.git_providers.git_provider import GitProvider
from app.exceptions import GitHubAPIError

class GitHubProvider(GitProvider):
    """GitHub API 提供者实现，封装 GitHub REST API 调用"""
    
    def __init__(self, token: str) -> None:
        """初始化 GitHub 提供者
        
        Args:
            token: GitHub 个人访问令牌 (PAT)
        """
        self.token = token

    def _headers(self) -> dict[str, str]:
        """生成 GitHub API 请求头
        
        Returns:
            包含认证和版本信息的请求头字典
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",  # 固定 API 版本，避免兼容性问题
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def list_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """获取 PR 中修改的文件列表
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            pr_number: PR 编号
            
        Returns:
            文件信息列表，每个文件包含路径、状态等信息
            
        Raises:
            GitHubAPIError: GitHub API 调用失败时抛出
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers(), timeout=20.0)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(f"HTTPStatusError getting PR files: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise GitHubAPIError(f"Error getting PR files: {e}") from e

    async def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """获取 PR 的详细信息
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            pr_number: PR 编号
            
        Returns:
            PR 详细信息字典，包含标题、描述、分支信息等
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers(), timeout=20.0)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(f"HTTPStatusError getting PR info: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise GitHubAPIError(f"Error getting PR info: {e}") from e

    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """获取 PR 的原始差异文本
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            pr_number: PR 编号
            
        Returns:
            原始差异文本（unified diff 格式）
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.diff"  # 请求 diff 格式
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=20.0)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(f"HTTPStatusError getting PR diff: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise GitHubAPIError(f"Error getting PR diff: {e}") from e

    async def publish_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> int:
        """在 PR 上发布评论
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            pr_number: PR 编号
            body: 评论内容（Markdown 格式）
            
        Returns:
            创建的评论 ID
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=self._headers(), json={"body": body}, timeout=20.0)
                resp.raise_for_status()
                return resp.json().get("id")
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(f"HTTPStatusError publishing PR comment: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise GitHubAPIError(f"Error publishing PR comment: {e}") from e

    async def update_pr_comment(self, owner: str, repo: str, comment_id: int, body: str) -> None:
        """更新已存在的 PR 评论
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            comment_id: 要更新的评论 ID
            body: 新的评论内容
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.patch(url, headers=self._headers(), json={"body": body}, timeout=20.0)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(f"HTTPStatusError updating PR comment: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise GitHubAPIError(f"Error updating PR comment: {e}") from e

    async def get_pr_check_runs(self, owner: str, repo: str, head_sha: str) -> list[dict]:
        """获取指定提交的检查运行状态（CI/CD 状态）
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            head_sha: 提交 SHA
            
        Returns:
            检查运行状态列表，包含 CI 检查结果
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers(), timeout=20.0)
                resp.raise_for_status()
                data = resp.json()
                return data.get("check_runs", [])
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(f"HTTPStatusError getting check runs: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise GitHubAPIError(f"Error getting check runs: {e}") from e
