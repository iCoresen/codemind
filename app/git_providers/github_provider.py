from typing import Any
import httpx

from app.git_providers.git_provider import GitProvider

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
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(), timeout=20.0)
            resp.raise_for_status()
            return resp.json()

    async def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(), timeout=20.0)
            resp.raise_for_status()
            return resp.json()

    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.diff"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=20.0)
            resp.raise_for_status()
            return resp.text

    async def publish_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=self._headers(), json={"body": body}, timeout=20.0)
            resp.raise_for_status()
        resp.raise_for_status()