from typing import Any
import asyncio
import logging
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
        transport = httpx.AsyncHTTPTransport(retries=3)
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(20.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

    async def close(self) -> None:
        """清理连接池资源"""
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        """生成 GitHub API 请求头

        Returns:
            包含认证和版本信息的请求头字典
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试和限流处理的请求封装

        Args:
            method: HTTP 方法
            url: 请求 URL
            **kwargs: 传递给 httpx 请求的其他参数

        Returns:
            httpx.Response 对象

        Raises:
            GitHubAPIError: 当重试耗尽或发生不可恢复错误时
        """
        max_retries = 3
        retry_count = 0

        while retry_count <= max_retries:
            try:
                response = await self._client.request(method, url, **kwargs)

                # 处理限流 (403)
                if response.status_code == 403:
                    reset_header = response.headers.get("X-RateLimit-Reset")
                    if reset_header:
                        import time
                        reset_time = int(reset_header)
                        wait_seconds = max(reset_time - time.time(), 1)
                        logger = logging.getLogger("codemind.github")
                        logger.warning(f"Rate limited. Waiting {wait_seconds}s for rate limit reset.")
                        await asyncio.sleep(wait_seconds)
                        retry_count += 1
                        continue
                    # 没有 rate limit info，可能是权限问题
                    raise GitHubAPIError(f"GitHub API 403 Forbidden: {response.text}")

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                # 非限流的 HTTP 错误
                raise GitHubAPIError(f"HTTPStatusError: {e.response.status_code} - {e.response.text}") from e
            except httpx.Timeout:
                retry_count += 1
                if retry_count <= max_retries:
                    await asyncio.sleep(2 ** retry_count)  # 指数退避
                    continue
                raise GitHubAPIError(f"Request timeout after {max_retries} retries")
            except Exception as e:
                raise GitHubAPIError(f"Request error: {e}") from e

        raise GitHubAPIError(f"Max retries ({max_retries}) exceeded")

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
        resp = await self._request_with_retry("GET", url, headers=self._headers())
        return resp.json()

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
        resp = await self._request_with_retry("GET", url, headers=self._headers())
        return resp.json()

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
        headers["Accept"] = "application/vnd.github.v3.diff"
        resp = await self._request_with_retry("GET", url, headers=headers)
        return resp.text

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
        resp = await self._request_with_retry(
            "POST", url, headers=self._headers(), json={"body": body}
        )
        return resp.json().get("id")

    async def update_pr_comment(self, owner: str, repo: str, comment_id: int, body: str) -> None:
        """更新已存在的 PR 评论

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            comment_id: 要更新的评论 ID
            body: 新的评论内容
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
        await self._request_with_retry(
            "PATCH", url, headers=self._headers(), json={"body": body}
        )

    async def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """获取 PR 的 commit 列表

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            pr_number: PR 编号

        Returns:
            commit 列表，每项包含 sha, message, author 等信息
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/commits"
        resp = await self._request_with_retry("GET", url, headers=self._headers())
        commits = resp.json()
        return [
            {
                "sha": c.get("sha", "")[:8],
                "message": c.get("commit", {}).get("message", ""),
                "author": c.get("commit", {}).get("author", {}).get("name", ""),
            }
            for c in commits
        ]

    async def get_recent_commits(self, owner: str, repo: str, since: str = None) -> list[dict]:
        """获取仓库最近的 commit 列表

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            since: 可选的时间字符串，格式如 2023-01-01T00:00:00Z

        Returns:
            commit 列表
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {"per_page": 100}
        if since:
            params["since"] = since
        resp = await self._request_with_retry("GET", url, headers=self._headers(), params=params)
        commits = resp.json()
        return [
            {
                "sha": c.get("sha", "")[:8],
                "message": c.get("commit", {}).get("message", ""),
                "author": c.get("commit", {}).get("author", {}).get("name", ""),
            }
            for c in commits
        ]

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """获取指定 ref（分支/commit SHA）下的文件内容

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            path: 文件路径
            ref: Git ref（分支名或 commit SHA）

        Returns:
            文件内容文本（UTF-8）
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.raw"
        resp = await self._request_with_retry("GET", url, headers=headers, params={"ref": ref})
        return resp.text

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
        resp = await self._request_with_retry("GET", url, headers=self._headers())
        data = resp.json()
        return data.get("check_runs", [])

    async def get_pr_comments(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """获取PR的所有评论

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            pr_number: PR编号

        Returns:
            评论列表，每项包含id、body、user等信息

        Raises:
            GitHubAPIError: GitHub API调用失败时抛出
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        resp = await self._request_with_retry("GET", url, headers=self._headers())
        return resp.json()
