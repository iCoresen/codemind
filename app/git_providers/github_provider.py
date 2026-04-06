from typing import Any
import httpx

from app.git_providers.git_provider import GitProvider
from app.exceptions import GitHubAPIError

class GitHubProvider(GitProvider):
    def __init__(self, token: str) -> None:
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def list_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
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
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.diff"
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