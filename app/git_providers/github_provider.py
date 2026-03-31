from typing import Any
import requests

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

    def list_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        resp = requests.get(url, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        return resp.json()

    def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        resp = requests.get(url, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        return resp.json()

    def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = self._headers()
        headers["Accept"] = "application/vnd.github.v3.diff"
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.text

    def publish_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        resp = requests.post(url, headers=self._headers(), json={"body": body}, timeout=20)
        resp.raise_for_status()