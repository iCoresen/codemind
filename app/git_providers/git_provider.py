from abc import ABC, abstractmethod
from typing import Any

class GitProvider(ABC):
    """Git 提供者抽象基类"""
    
    @abstractmethod
    async def list_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        pass
        
    @abstractmethod
    async def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        pass
        
    @abstractmethod
    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        pass
        
    @abstractmethod
    async def publish_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> int:
        pass

    @abstractmethod
    async def update_pr_comment(self, owner: str, repo: str, comment_id: int, body: str) -> None:
        pass

    @abstractmethod
    async def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        pass

    @abstractmethod
    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        pass

    @abstractmethod
    async def get_pr_check_runs(self, owner: str, repo: str, head_sha: str) -> list[dict]:
        pass
