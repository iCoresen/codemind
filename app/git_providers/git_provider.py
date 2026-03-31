from abc import ABC, abstractmethod
from typing import Any


class GitProvider(ABC):
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
    async def publish_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        pass